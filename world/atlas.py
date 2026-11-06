# -*- coding: utf-8 -*-
"""**三级底图**：把"这本书的地方长什么样"在开卷时定下来，之后各轮复用。

用户 2026-10-08 的原话（这段就是本模块的全部规格）：

    「设定集里是否可以包含某个房屋的地图，另外 是否可以在开卷的时候把一些
      **整体地图 局部地图** (房屋附近 房屋内部 以及别的需要的地图)**提前画好**
      需要的时候**基于这些地图让美术加细节**」

## 为什么需要它

在这之前，小地图是**美术每天凭空摆位**：`crew/agents.draw_day_map()` 拿到的
只有「今天这几处地点 + 今天的分拍」，**没有任何空间事实**。后果有两条：

1. **同一处地方位置飘**：今天的戏在茶肆和渡口 → 茶肆被排在左上；
   明天还是这两处 → 可能被排在右下。"地图"于是不是地图，是每天的插图。
2. **室内根本画不出来**：最小粒度只有"一处地点"这一个点，
   「人在楼里哪一层、哪个屋」这件事在图上无处安放。

用户要的是**先有底图，再按需取景**。这就是本模块。

## 三层（三层是**同一套坐标**的不同缩放层级）

| 层 | 画什么 | 坐标范围 | 谁在用 |
|---|---|---|---|
| `整体` | 地点之间的**方位与通路**（城/镇/村一级） | 全图 0~1 | 今天的戏**跨了地方**时 |
| `局部` | **某一处地点周边**（河、桥、邻舍、门外） | 全图 0~1 | 今天戏在**同一处**时 |
| `室内` | **房屋内部**（堂屋 / 后院 / 侧案 / 井 / 柜台） | 全图 0~1 | 今天戏**在屋里换屋子**时 |

★ 三层各自是一份完整的 `Layout`（就是 `image_gen/map_layout.Layout`）——
  它们**不共享坐标系**，各画各的，因为画布只有 200×126 那么点大：
  "整体图上再套一个放大的室内"在这么小的画布上只会糊成一团。
  取景的规则是「**今天最细的那一层**说了算」，见 `pick_layers()`。

## 存哪：`设定集/小世界地图.yaml`

这个文件**本来就在**（`ingest/pipeline._freeze` 一直在写
`{"名称": "待生成", "地点": []}` 这个占位），配套的 `world/map.py` 里那个
`GameMap` 也一直在，但**从来没有人生成过、也没有人读过** ——
`build_map()` 因为空表永远返回 `None`，挂到主循环上的 `game_map` 无人问津。
本模块把它接上：**占位 → 真底图**。

⚠ 与「肖像」（`image_gen/portraits.py`）是**同一套模式**：项目级位置、
开卷一次生成、之后跨轮复用、拿不到就如实说。

## ⚠ 一条硬规矩：底图**不是凭空编的**

每层底图里的名字必须**来自设定**（`地点.yaml` 的地点，或该地点的 `内里`）。
模型编出来的名字一律丢掉（复用 `map_layout.normalize()` 的白名单过滤）。
"画一个设定里没有的地方"就是**编**，这个项目最忌讳这个。

English:
**three-level base map**: fix down "what the places in this book look like" when the volume is
opened, and reuse it in later rounds.
the user's exact words on 2026-10-08 (this passage is the entire spec of this module):
    "Can the setting collection include a map of some house, and also, can we at volume-open time
     **draw in advance** some **whole map, local map** (house surroundings, house interior, and other needed maps)
     and when needed **add detail to these maps via the art**"
## why it's needed
before this, the mini-map was **the art凭空 placing positions every day**: what
`crew/agents.draw_day_map()` got
was only "today's few locations + today's shot breakdown", **with no spatial facts at all**. Two
consequences:
1. **the same place drifts in position**: today's scene is at the tea house and the ferry → the tea house gets placed top-left;
   tomorrow it's still these two places → they may get placed bottom-right. The "map" is then not a map, it's a daily illustration.
2. **interiors simply cannot be drawn**: the smallest granularity is a single point, "one location",
   and "which floor, which room the person is in inside the building" has nowhere to go on the map.
what the user wants is **a base map first, then frame on demand**. That is this module.
## three layers (the three layers are different zoom levels of **the same coordinate system**)
| layer | what's drawn | coordinate range | who uses it |
|---|---|---|---|
| `整体` | **bearings and paths** between locations (city/town/village level) | whole map 0~1 | when today's scene **spans places** |
| `局部` | **surroundings of one location** (river, bridge, neighboring houses, outside the gate) | whole map 0~1 | when today's scene is **in the same place** |
| `室内` | **inside the house** (main hall / backyard / side desk / well / counter) | whole map 0~1 | when today's scene **moves between rooms indoors** |
★ each of the three layers is a complete `Layout` (that is `image_gen/map_layout.Layout`) ——
  they **do not share a coordinate system**, each draws its own, because the canvas is only 200×126, so small:
  "putting an enlarged interior on top of the whole map" on such a small canvas would only turn into a blurry mess.
  the framing rule is "**the finest layer used today** decides", see `pick_layers()`.
this file **has always been there** (`ingest/pipeline._freeze` has always been writing
has always been there too, but **no one has ever generated it, and no one has ever read it** ——
`build_map()` always returns `None` for an empty table, and the `game_map` attached to the main
loop goes unused.
This module wires it up: **placeholder → real base map**.
⚠ It is the **same pattern** as "portraits" (`image_gen/portraits.py`): project-level location,
generated once at book start, reused across turns afterward, and if it can't be obtained, say so
honestly.
## ⚠ One hard rule: the base map is **not made up out of thin air**
The names in each layer's base map must **come from the setting** (locations in `地点.yaml`, or
that location's `内里`).
Names invented by the model are all discarded (reuse `map_layout.normalize()`'s whitelist
filtering).
"Drawing a place that isn't in the setting" is **making things up**, which this project most
frowns upon.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from image_gen.map_layout import Layout, normalize

_LOG = logging.getLogger('nws.atlas')

#: 设定集里的文件名（**别改**：改了等于把老项目的底图全丢了）
# [EN] : filename in the setting collection (**do not change**: changing it means losing all the base
# [EN] maps of the old project)
FILE = '小世界地图.yaml'

#: 三层（顺序 = 从粗到细；`pick_layers()` 依赖这个顺序）
# [EN] : three layers (order = coarse to fine; `pick_layers()` depends on this order)
LAYERS = ('整体', '局部', '室内')


def apply_space_rules(lay, *, kind: str = '室内', building: str = '') -> list[str]:
    """把**空间常识**落到一份 `Layout` 上（用户 2026-10-12 点名的那件事）。

    做三件事，**只加不减**：

    1. **打标记**：`lay.kind` = 这一层是哪一层；`lay.frame` = 整座建筑的名字
       （室内层才有 —— 小地图据此把整座楼**框起来**，而不是在中间点一个红点）。
    2. **补院子**：有井（或别的屋外器物）却没有院子 → 补一个院子，
       并把院子摆在**井的旁边**（图上挨着才看得出"井在院里"）。
    3. **报违规**：修完还剩下的（`重名`/`器物入屋`/`房间出屋`）作为说明返回，
       由调用方记进日志 —— **不悄悄改名字，也不假装没这回事**。

    ⚠ 为什么留在这个名字下：**调用点说人话** —— `ingest/atlas` 读起来是
      "给底图过一遍空间常识"，而不用关心实现放在哪一层。
      ⚠ **实现只有一份**，在 `image_gen/map_layout.apply_space_rules`：
        那边同时有 `Layout` 与 `Place`，而且**当天的图**（`day_layout`）也要用同一份。
        别在这里再写第二份 —— 底图画了院子、当天的图又没了，比两处都没有更糟。
    [EN] ⚠ Why it keeps this name: **so call sites read plainly** -- `ingest/atlas` reads as "run
    [EN] spatial common sense over the base map", without caring which layer the implementation is on.
    [EN] ⚠ **There is exactly one implementation**, in `image_gen/map_layout.apply_space_rules`: that
    [EN] module has both `Layout` and `Place`, and **the day's map** (`day_layout`) needs the same one.
    [EN] Do not write a second copy here -- the base map drawing a courtyard while the day's map drops it
    [EN] is worse than neither having one.
    """
    from image_gen.map_layout import apply_space_rules as _impl
    return _impl(lay, kind=kind, building=building)





#: 位图底画的目录（项目级，与 `<项目>/肖像/` 并列）
# [EN] : directory for bitmap base art (project-level, parallel to `<项目>/肖像/`)
BITMAP_DIRNAME = '地图'


@dataclass
class Atlas:
    """一本书的三级底图。任何一层都可以缺（缺了退回更粗的一层）。
        English:
    A book's three-level base maps. Any layer may be missing (if missing, fall back to a coarser
    layer).
    """

    name: str = ''
    #: L1 整体（地点之间的方位与通路）
    # [EN] : L1 whole (bearings and paths between locations)
    overview: Layout | None = None
    #: L2 局部：`{地点名: Layout}`（该处周边）
    # [EN] : L2 local: `{地点名: Layout}` (surroundings of that place)
    local: dict[str, Layout] = field(default_factory=dict)
    #: L3 室内：`{地点名: Layout}`（该处内部）
    # [EN] : L3 interior: `{地点名: Layout}` (inside that place)
    indoor: dict[str, Layout] = field(default_factory=dict)
    #: 位图氛围底画：`[{层, 地点, 文件}]`（相对设定集目录的路径）
    # [EN] : bitmap ambience base art: `[{层, 地点, 文件}]` (paths relative to the setting collection directory)
    bitmaps: list[dict] = field(default_factory=list)
    #: 这份底图是**依据哪些地点**生成的（`地点.yaml` 的名字表）。
    #: 重开卷时拿它比对：地点表没变就**不重画**（省一次生成）。
    # [EN] : which locations this base map was generated **from** (the name table in `地点.yaml`).
    # [EN] : compare against it when reopening the volume: if the location table hasn't changed, **don't
    # [EN] redraw** (saves one generation).
    basis: list[str] = field(default_factory=list)
    #: **依据的指纹**（名字 + 说明 + 内里 一起算）。
    #: ⚠ 为什么不能只比名字：用户开卷后**手改设定集**是很正常的事
    #   （§4.1 那条技巧），而他最可能改的就是"说明"——
    #   "临河的茶楼，两层，后院有口井" 改成 "…后院有口井和一间柴房"，
    #   名字一个没变。只比名字的话底图**永远不会跟上**，
    #   而且界面上一切正常（"我改了怎么没用"是最难查的一类）。
    # [EN] : **fingerprint of the basis** (name + description + interior computed together).
    # [EN] : ⚠ why we can't compare names only: after the user opens the volume, **hand-editing the setting
    # [EN] collection** is perfectly normal
    # [EN] (the trick in §4.1), and what he's most likely to edit is the "description" ——
    # [EN] not a single name changed. If we compare names only, the base map will **never keep up**,
    # [EN] and everything looks fine in the UI ("I changed it, why doesn't it work" is the hardest kind of
    # [EN] bug to track down).
    fingerprint: str = ''
    #: 生成时间（给人看的；程序不依赖它）
    # [EN] : generation time (for humans; the program does not depend on it)
    made_at: str = ''

    # ── 查询 ──────────────────────────────────────────────────
    # [EN] ── query ──────────────────────────────────────────────────
    def resolve_here(self, here: str) -> str:
        """把「现在人在哪儿」落到**底图里的某个地点名**上。

        ★★ 为什么需要这一步（2026-10-08 用户报的 bug）：
          `world.scene` 与分拍的「场」经常是**子地点**，不是地点表里的名字 ——
          「临河茶肆堂内」「后院」「柜台前」这种。而底图的键是**地点名**
          （`临河茶肆`）。拿"临河茶肆堂内"直接查键**永远查不到** → 于是
          人明明站在楼里，取景却一路跌到 ②「整体」，屏幕上出现的是
          **整座城的方位图**。用户原话：
          「如果是就在楼里面的话 楼里的平面图为何没生成 放到小地图里」。

        做法（两层匹配，都是**双向包含**）：

          ① 先拿**层名/地点名**（`indoor` / `local` / `basis` 的键）比；
          ② 不行再拿**层里画的那些名字**比 —— 因为 `here` 有时是**房间名**
             （"后院""堂屋"），它只存在于某个室内层的**内部**，不在任何键上。
             第 ① 层匹配不到它，得靠"哪个层里画了它"反查出那一层。

        命中多个取**最长**的（"临河茶肆"比"临河"更具体）。
        都找不到就原样返回 —— 调用方照旧走"没有这一层"的路（不编一个地点出来）。
        
                English:
        Map "where the person is now" onto **a certain location name in the base map**.
                ★★ Why this step is needed (bug reported by user on 2026-10-08):
                  `world.scene` and the "scene" of the shot breakdown are often **sub-locations**, not names in the location table —
                  even though the person is clearly standing in the building, the framing falls all the way to ② "整体", and what appears on screen is
                  **the bearing map of the whole city**. The user's exact words:
                  "if it's inside the building, why wasn't the floor plan of the building generated and put in the minimap".
                Approach (two-level matching, both **bidirectional containment**):
                  ① First compare using the **layer name / location name** (the keys of `indoor` / `local` / `basis`);
                  ② If that fails, compare using **the names drawn in the layers** — because `here` is sometimes a **room name**
                     ("后院" "堂屋"), which only exists **inside** some indoor layer, not on any key.
                     Level ① can't match it; you have to reverse-look-up which layer has it drawn in it.
                If none is found, return as-is — the caller goes down the "no such layer" path as before (do not make up a location).
        """
        h = str(here or '').strip()
        if not h:
            return ''
        keys = set(self.indoor) | set(self.local) | set(self.basis)
        if h in keys:
            return h                                    # 精确命中，直接用
            # [EN] exact hit, use directly
        cands = [k for k in keys if k and (k in h or h in k)]
        if cands:
            return max(cands, key=len)                  # 最长 = 最具体
        # ② 再看**层里画的那些名字**（房间名 → 反查它属于哪一层）
            # [EN] longest = most specific
            # [EN] ② then look at **the names drawn in the layer** (room name → reverse-lookup which layer it
            # [EN] belongs to)
        for bucket in (self.indoor, self.local):
            for key, lay in bucket.items():
                if key == h:
                    return key
                for p in (getattr(lay, 'places', None) or []):
                    if p.name and (p.name == h or p.name in h or h in p.name):
                        return key
        return h

    def layers_for(self, places: list[str] | None,
                   here: str = '') -> list[tuple[str, str, Layout]]:
        """今天该用哪几层：返回 `[(层名, 地点名, Layout), …]`。

        ★ 取景规则（一句话）：**今天最细的那一层说了算**。

        | 今天的样子 | 用哪层 |
        |---|---|
        | 戏只在**一处**，但**那处的室内**有戏（分拍里出现了屋内的位置） | `室内` 那一层 |
        | 戏只在**一处**，室内层没有 | `局部` |
        | 戏**跨了两处以上** | `整体` |

        `here`（现在人在哪儿）永远优先试它自己的细层 —— "人在哪儿"是最硬的一条。
        返回**空列表**表示"这份底图管不了今天"（调用方退回原来的做法）。

        ⚠ `here` 要先经 `resolve_here()` 归一到地点名上：它常常是**子地点**
          （"临河茶肆堂内"），直接查键查不到 → 会误判成"跨了地方"而退回整体图。
        
                English:
        Which layers to use today: returns `[(layer_name, location_name, Layout), …]`.
                ★ Framing rule (in one sentence): **the finest layer for today has the final say**.
                | Today's situation | Which layer to use |
                |---|---|
                | The action is only in **one place**, but **that place's interior** has action (positions inside the room appear in the shot breakdown) | the `室内` layer |
                | The action is only in **one place**, no indoor layer | `局部` |
                | The action **spans two or more places** | `整体` |
                `here` (where the person currently is) always tries its own fine layer first -- "where the person is" is the hardest rule.
                Returning an **empty list** means "this basemap can't handle today" (the caller falls back to the original approach).
                ⚠ `here` must first be normalized to a place name via `resolve_here()`: it is often a **sub-location**
                  ("临河茶肆堂内"), which can't be found by direct key lookup → it would be misjudged as "crossed to another place" and fall back to the overall map.
        """
        names = [str(x).strip() for x in (places or []) if str(x).strip()]
        h = self.resolve_here(here)
        # 今天涉及的地点也归一化（同样可能是子地点写法），并去掉与 `h` 重复的
        # [EN] locations involved today are also normalized (may likewise be written as sub-locations), and
        # [EN] those duplicated with `h` are removed
        norm = [self.resolve_here(n) for n in names]
        uniq: list[str] = []
        for n in norm:
            if n and n not in uniq:
                uniq.append(n)
        # ① 只在一处（或本就在一处）→ 先试室内，再试局部
        # [EN] ① only in one place (or originally in one place) → try interior first, then local
        if h and (len(uniq) <= 1 or uniq == [h]):
            if h in self.indoor:
                return [('室内', h, self.indoor[h])]
            if h in self.local:
                return [('局部', h, self.local[h])]
            # `h` 归一之后没层，但"今天涉及的那一处"有层 → 用它（同一处地方）
            # [EN] after normalizing `h` there's no layer, but "the one place involved today" has a layer → use it
            # [EN] (same place)
            for n in uniq:
                if n in self.indoor:
                    return [('室内', n, self.indoor[n])]
                if n in self.local:
                    return [('局部', n, self.local[n])]
        # ② 跨了地方 → 用整体
        # [EN] ② spans places → use whole
        if self.overview is not None:
            return [('整体', '', self.overview)]
        # ③ 没有整体图，退而求其次：有哪处的局部就用哪处
        # [EN] ③ no whole map, settle for less: use whichever place's local map exists
        for n in ([h] if h else []) + uniq:
            if n in self.local:
                return [('局部', n, self.local[n])]
        return []

    def has_any(self) -> bool:
        """有没有任何一层（空底图等于没有底图 —— 界面要照实说）。
                English:
        Is there any layer at all (an empty basemap equals no basemap -- the UI must say so honestly).
        """
        return bool(self.overview or self.local or self.indoor)

    # ── 存取 ──────────────────────────────────────────────────
    # [EN] ── storage ──────────────────────────────────────────────────
    def to_dict(self) -> dict:
        out: dict[str, Any] = {'名称': self.name or '小世界地图'}
        if self.made_at:
            out['生成时间'] = self.made_at
        if self.basis:
            out['依据'] = list(self.basis)
        if self.fingerprint:
            out['依据指纹'] = self.fingerprint
        if self.overview is not None:
            out['整体'] = self.overview.to_dict()
        if self.local:
            out['局部'] = {k: v.to_dict() for k, v in self.local.items()}
        if self.indoor:
            out['室内'] = {k: v.to_dict() for k, v in self.indoor.items()}
        if self.bitmaps:
            out['位图'] = list(self.bitmaps)
        # ⚠ 顶层保留一个空的 `地点`：老代码（`world/map.GameMap`）按它判断
        #   "这份地图有没有内容"。留一个空数组，比让它 KeyError 强。
        # [EN] ⚠ keep an empty `地点` at the top level: old code (`world/map.GameMap`) uses it to decide
        # [EN] "whether this map has content". Keeping an empty array is better than letting it KeyError.
        out.setdefault('地点', [])
        return out

    @classmethod
    def from_dict(cls, data: Any) -> 'Atlas | None':
        """从 `小世界地图.yaml` 读回。**没有底图时返回 `None`**（不是空 Atlas）。

        ⚠ 为什么返回 None 而不是空对象：调用方要能区分
          「这本书还没生成过底图」与「生成了但一层都没有」——
          前者该去生成，后者该**如实告诉用户生成失败了**。都返回空对象的话，
          这两种情况在界面上长得一模一样。
        
                English:
        Read back from `小世界地图.yaml`. **Return `None` when there is no basemap** (not an empty Atlas).
                ⚠ Why return None instead of an empty object: the caller must be able to distinguish
                  "this book has never generated a basemap" from "it was generated but has zero layers" --
                  the former should go generate one, the latter should **honestly tell the user that generation failed**. If both returned an empty object,
                  these two cases would look exactly the same in the UI.
        """
        if not isinstance(data, dict):
            return None
        at = cls(name=str(data.get('名称') or '').strip())
        at.made_at = str(data.get('生成时间') or '').strip()
        at.fingerprint = str(data.get('依据指纹') or '').strip()
        basis = data.get('依据')
        at.basis = [str(x).strip() for x in basis if str(x).strip()] \
            if isinstance(basis, list) else []

        if isinstance(data.get('整体'), dict):
            names = [str(x).strip() for x in (data.get('依据') or []) if str(x).strip()]
            at.overview = normalize(data['整体'], names, source='atlas')
            if at.overview is not None and not at.overview.kind:
                # ★ 老缓存兜底：整体层没有 `kind` 时按桶名补上（见下面那段说明）。
                # [EN] Backfill for old caches: when the whole-map layer has no `kind`, fill it from
                # [EN] the bucket name (see the note below).
                at.overview.kind = LAYERS[0]
        for key, bucket in (('局部', at.local), ('室内', at.indoor)):
            raw = data.get(key)
            if not isinstance(raw, dict):
                continue
            for place, lay in raw.items():
                p = str(place or '').strip()
                if not p or not isinstance(lay, dict):
                    continue
                # ⚠ 室内/局部层里的名字**不在 `地点.yaml` 里**（它们是房间名），
                #   所以这里传**空的 names** = 不做白名单过滤。
                #   `normalize()` 的写法是 `if allowed and …` —— 空表不过滤。
                # [EN] ⚠ names in the interior/local layers **are not in `地点.yaml`** (they are room names),
                # [EN] so here we pass **empty names** = no whitelist filtering.
                # [EN] `normalize()` is written as `if allowed and …` —— an empty table does not filter.
                got = normalize(lay, [], source='atlas')
                if got and got.places:
                    # ★★★ **老缓存兜底：按桶名把 `kind` / `frame` 补回来**（2026-10-12）。
                    #   用户报「现在的小地图中间都有一个红点 这个去掉 看不见其他元素了」。
                    #   根因有两个，**这一处是第二个**（第一个在 `normalize()` 没读这两个键）：
                    #   用户手上那份 `小世界地图.yaml` 是在"室内语义"加进去**之前**生成的，
                    #   文件里根本没有 `kind` / `frame` 两个键。所以哪怕 `normalize()`
                    #   修好了，老文件读回来照样是空的 ⇒ 红点照旧。
                    #   **桶名本身就说明了它是哪一层**（它在 `室内` 字典里，那就是室内层），
                    #   所以这里能确定性地补上，不用重画底图、也不用重新开卷：
                    #     · 桶 = `室内` → `kind='室内'`，`frame=` 这个桶的键（= 地点名，
                    #       正好就是"整座建筑的名字"）；
                    #     · 桶 = `局部` → `kind='局部'`（**不补 frame**：局部图不该框建筑）。
                    #   ⚠ 只在**缺**的时候补（`not got.kind`）—— 文件里写了的以文件为准。
                    # [EN] ★★★ **Backfill for old caches: restore `kind` / `frame` from the bucket name**
                    # [EN] (2026-10-12).
                    # [EN]   The user reported "every minimap now has a red dot in the middle; remove it,
                    # [EN]   it hides the other elements."
                    # [EN]   There were two root causes, **this is the second** (the first is that
                    # [EN]   `normalize()` never read these two keys):
                    # [EN]   the `小世界地图.yaml` in the user's hands was generated **before** the
                    # [EN]   "indoor semantics" existed, so the file has neither key at all. So even with
                    # [EN]   `normalize()` fixed, old files still read back empty ⇒ the red dot stays.
                    # [EN]   **The bucket name itself says which layer it is** (it sits in the `室内`
                    # [EN]   dict, so it is the indoor layer), so this can be filled in deterministically
                    # [EN]   without redrawing the base map or reopening the book:
                    # [EN]     · bucket = `室内` → `kind='室内'`, `frame=` this bucket's key (= the
                    # [EN]       location name, which is exactly "the whole building's name");
                    # [EN]     · bucket = `局部` → `kind='局部'` (**no frame**: a local map should not
                    # [EN]       frame the building).
                    # [EN]   ⚠ Only fill when **missing** (`not got.kind`) -- what the file says wins.
                    if not got.kind:
                        got.kind = LAYERS[2] if key == '室内' else LAYERS[1]
                    if key == '室内' and not got.frame:
                        got.frame = p
                    bucket[p] = got
        if isinstance(data.get('位图'), list):
            at.bitmaps = [{str(k): v for k, v in it.items()}
                          if isinstance(it, dict) else {} for it in data['位图']]
            at.bitmaps = [b for b in at.bitmaps if b]

        return at if at.has_any() else None


# ══════════════════════════════════════════════════════════════════
#  落盘 / 读回
# [EN] save to disk / read back
# ══════════════════════════════════════════════════════════════════
def load(settings_dir: Path | str | None) -> Atlas | None:
    """从设定集目录读底图。读不到 / 坏了 / 只是个占位 → `None`，不抛。
        English:
    Read the base map from the setting collection directory. Unreadable / broken / just a
    placeholder → `None`, no throw.
    """
    if not settings_dir:
        return None
    p = Path(settings_dir) / FILE
    if not p.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding='utf-8'))
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning('底图读不出来（当没有底图）：%s · %r', p.name, e)
        return None
    return Atlas.from_dict(data)


def save(settings_dir: Path | str, atlas: Atlas) -> bool:
    """写回设定集。**失败不抛**（底图不是推演的生死线），但要吭一声。
        English:
    Write back to the setting collection. **Failure does not throw** (the base map is not the
    lifeline of the simulation), but sound off about it.
    """
    try:
        import yaml
        from util.io import atomic_write_text
        p = Path(settings_dir) / FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(p, yaml.dump(atlas.to_dict(), allow_unicode=True,
                                       default_flow_style=False, sort_keys=False))
        return True
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning('底图写盘失败（这一轮会退回"每天现画"）：%r', e)
        return False


def fingerprint_of(places: list[str], briefs: list[str] | None = None) -> str:
    """依据的**指纹**：地点名 + 说明（+ 内里，如果说明里写着）一起算。

    ★ 只比名字是不够的（见 `Atlas.fingerprint` 那段）：
      用户手改的往往是**说明** —— "后院有口井" → "后院有口井和一间柴房"，
      名字一个没变。比名字的话底图永远不跟上，而界面上一切正常。

    ⚠ 排序后再算：`地点.yaml` 里两条换个位置不该让底图重画
      （位置是我们在底图里定的，跟他在文件里的书写顺序无关）。
    
        English:
    The **fingerprint** it's based on: location name + description (+ 内里, if written in the
    description) computed together.
        ★ Comparing names alone is not enough (see the `Atlas.fingerprint` section):
          what users manually edit is often the **description** — "the backyard has a well" → "the backyard has a well and a woodshed",
          not a single name changed. If you compare names, the base map never keeps up, while on the UI everything looks normal.
        ⚠ Compute after sorting: swapping the positions of two entries in `地点.yaml` should not cause the base map to be redrawn
          (positions are decided by us in the base map, unrelated to the order in which they're written in the file).
    """
    import hashlib
    bs = list(briefs or [])
    rows = []
    for i, n in enumerate(places or []):
        b = bs[i] if i < len(bs) else ''
        rows.append(f'{str(n).strip()}|{str(b).strip()}')
    blob = '\n'.join(sorted(rows))
    return hashlib.md5(blob.encode('utf-8')).hexdigest()[:12]


def same_basis(atlas: Atlas | None, places: list[str],
               briefs: list[str] | None = None) -> bool:
    """底图**是不是照着这份地点表生成的**（是 → 重开卷时不必重画）。

    ⚠ 比较的是**名字的多重集合**（不比顺序）：用户把 `地点.yaml` 里两条调个位置，
      底图不该重画（位置是我们在底图里定的，跟他在文件里的书写顺序无关）。
    ⚠ 有指纹时**按指纹比**（说明改了一个字也要重画）；老底图没有指纹 → 退回比名字
      （"老项目不至于因为升级一次就把底图全部重画一遍"）。
    
        English:
    Whether the base map **was generated from this location table** (if yes → no need to redraw when
    reopening the book).
        ⚠ What's compared is the **multiset of names** (not order): if the user swaps the positions of two entries in `地点.yaml`,
          the base map should not be redrawn (positions are decided by us in the base map, unrelated to the order in which they're written in the file).
        ⚠ When a fingerprint exists, **compare by fingerprint** (changing one character in the description requires a redraw); old base maps have no fingerprint → fall back to comparing names
          ("an old project shouldn't have all its base maps redrawn just because of one upgrade").
    """
    if atlas is None:
        return False
    if atlas.fingerprint:
        return atlas.fingerprint == fingerprint_of(places, briefs)
    if not atlas.basis:
        return False
    return sorted(str(x).strip() for x in atlas.basis) == \
        sorted(str(x).strip() for x in (places or []))


def place_names(settings: dict) -> list[str]:
    """`地点.yaml` 里的地点名（读不到就是空 —— 空则无从生成底图）。
        English:
    Location names in `地点.yaml` (empty if unreadable — if empty, there is no way to generate a base
    map).
    """
    out: list[str] = []
    for it in (settings.get('places') or []):
        if isinstance(it, dict):
            n = str(it.get('名称') or '').strip()
        else:
            n = str(it or '').strip()
        if n and n not in out:
            out.append(n)
    return out


def place_brief(settings: dict, name: str) -> str:
    """某处地点的**既有说明**（`地点.yaml` 的 20 字那句）—— 生成底图时的唯一事实来源。
        English:
    The **existing description** of a location (the 20-character sentence in `地点.yaml`) — the sole
    source of truth when generating the base map.
    """
    for it in (settings.get('places') or []):
        if isinstance(it, dict) and str(it.get('名称') or '').strip() == name:
            return str(it.get('说明') or '').strip()
    return ''


def place_detail(settings: dict, name: str) -> str:
    """某处地点的**全部可用信息**：说明 + 方位 + 内里（作者写了才带上）。

    ★ 为什么要把 `方位` / `内里` 拼进去：作者写这两个字段**就是为了让底图更准**
      （见《设定写作指导》§3.5）。拼进提示词它才真的用得上 ——
      不拼的话字段存下来了、底图却还是按"说明 + 常识"推，
      作者看到的是"我明明写了柴房，图上怎么没有"。
    
        English:
    **All available information** about a location: description + bearing + 内里 (included only if the
    author wrote it).
        ★ Why `方位` / `内里` should be spliced in: the author wrote these two fields **precisely to make the base map more accurate**
          (see 《设定写作指导》§3.5). Only when spliced into the prompt do they actually get used —
          otherwise the fields are saved but the base map is still inferred from "description + common sense",
          and what the author sees is "I clearly wrote a woodshed, why isn't it on the map".
    """
    for it in (settings.get('places') or []):
        if not isinstance(it, dict) or str(it.get('名称') or '').strip() != name:
            continue
        bits = [str(it.get('说明') or '').strip()]
        if str(it.get('方位') or '').strip():
            bits.append(f'方位：{str(it["方位"]).strip()}')
        inner = it.get('内里')
        if isinstance(inner, list) and inner:
            bits.append('内里：' + '、'.join(str(x).strip() for x in inner if str(x).strip()))
        return '　'.join(x for x in bits if x)
    return ''
