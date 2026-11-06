"""**城市图**与**城际图**，两种新尺度的画法。

## 为什么要分开写，而不是把街道图放大

用户 2026-10-26：

> 「如果故事范围更大 我还希望由把房屋简略之后 绘制的城市地图（类似于高德地图那种）
>   城市之间的地图（类似标准地图 但是元素更少 ）」

原来的 `floorplan._draw_street` 只画"斜纹小方块＋名字＋连线"，它被**城市**与**城际**
两种尺度共用。后果是：两座隔着几百里的城，被画成两个相邻的小方块，中间一条线 ——
读者读不出"远"，也读不出"这一带是山地还是平原"。

两种尺度的**读法根本不同**：

| | 城市图（类高德） | 城际图（类标准地图·简化） |
|---|---|---|
| 主体 | **街区与路网**（面的分割） | **城镇与地形**（点与面） |
| 线 | 分级道路（宽窄可辨） | 官道/小路 + 河流 |
| 面 | 街区地块、水系、绿地 | 政区分区、水系、山地 |
| 点 | POI（地标大、普通小） | 城镇节点（按行政等级分符号） |
| 不画 | 房屋内部 | 街道、房屋 |

## 数据从哪来（不编）

两图都**只用手上有的**：

* 地点（`Place`：名字 / x,y / size / shape / note）—— 面的种子点；
* 通路（`layout.links`）—— 路的骨架；
* 水系（`layout.water`）—— 线，加宽成面；
* 风格档案（`worldstyle`）—— 决定标签用词与"这地方有没有城墙"这类默认。

**没有的东西一律不画**：不知道街区边界就画成一个整块，不知道路有多宽就按两端规模分级；
**绝不凭空生成一条不存在的路**（那比空白更坏：读者会拿它推理）。

街区用**确定性 Voronoi** 切：同一组地点永远切出同一片街区 ⇒ 与平面图同一个纪律
（延续性靠纯函数，不靠锁坐标）。
"""
from __future__ import annotations

import math

import flet as ft
import flet.canvas as fcv

from image_gen import minimap as MM
from image_gen import scale as SC
from image_gen import worldstyle as WS


# ══════════════════════════════════════════════════════════════════════
#  Voronoi：确定性地把画布切成"每个地点一块"
# [EN] Voronoi: deterministically cut the canvas into "one cell per place"
# ══════════════════════════════════════════════════════════════════════
def voronoi(seeds: list[tuple[str, float, float]],
            box: tuple) -> dict[str, list[tuple[float, float]]]:
    """按种子点把矩形 `box` 切成多边形（**半平面裁剪**，纯确定性，无随机）。

    Args:
        seeds: `[(名字, x, y), …]`（像素坐标）。
        box: `(x0, y0, x1, y1)`。

    Returns:
        `{名字: [(x, y), …]}` —— 每个地点的地块多边形（顶点按顺时针）。

    ## 算法
    对每个种子，从整个矩形开始，依次用"这两个点的垂直平分线"把多边形裁掉一半。
    O(n²)，n 是地点数（城市图通常 < 30）⇒ 够用，且**没有浮点抖动之外的随机性**。

    ★ 为什么不用库：`scipy.spatial.Voronoi` 会引入一个重依赖，而且它的输出是
      "无穷远的射线"要自己补边界 —— 补边界的代码一旦错，就会出现"地块漏出画框"。
      半平面裁剪的边界条件天然就是那个矩形，**不可能漏出去**。
    [EN] Cut a rectangle into polygons around the seeds (half-plane clipping; purely
    [EN] deterministic, no randomness). For each seed, start from the whole rectangle and clip away
    [EN] half the plane against the perpendicular bisector to every other seed. O(n^2), fine for
    [EN] fewer than ~30 places. ★ Why not a library: `scipy.spatial.Voronoi` adds a heavy dependency
    [EN] and returns infinite rays that must be clipped to the viewport -- and a bug there leaks
    [EN] cells outside the frame. Half-plane clipping's boundary *is* the rectangle, so it cannot
    [EN] leak.
    """
    x0, y0, x1, y1 = (float(v) for v in box)
    out: dict[str, list[tuple[float, float]]] = {}
    for i, (name, sx, sy) in enumerate(seeds):
        poly = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for j, (_, ox, oy) in enumerate(seeds):
            if i == j:
                continue
            poly = _clip_half(poly, sx, sy, ox, oy)
            if len(poly) < 3:
                break
        if len(poly) >= 3:
            out[name] = poly
    return out


def _clip_half(poly: list[tuple[float, float]],
               sx: float, sy: float, ox: float, oy: float) -> list[tuple[float, float]]:
    """保留多边形里**离 `s` 比离 `o` 更近**的那一半。

    判定量是 `f(p) = (p-o)² - (p-s)² = 2p·(s-o) + |o|² - |s|²`，`f > 0` 表示更靠近 s。
    这里用它的等价线性式，避免开方、避免除零。
    [EN] Keep the half of the polygon **closer to `s` than to `o`**. The test is the linear form of
    [EN] (p-o)^2 - (p-s)^2 > 0, avoiding square roots and division by zero.
    """
    ax, ay = sx - ox, sy - oy          # 法向（指向 s 一侧）
    # f(p) = 2*(p·(s-o)) - (|s|² - |o|²)
    c = (sx * sx + sy * sy) - (ox * ox + oy * oy)

    def f(px: float, py: float) -> float:
        return 2.0 * (px * ax + py * ay) - c

    out: list[tuple[float, float]] = []
    n = len(poly)
    for k in range(n):
        p = poly[k]
        q = poly[(k + 1) % n]
        fp, fq = f(*p), f(*q)
        if fp >= 0:
            out.append(p)
        if (fp > 0 and fq < 0) or (fp < 0 and fq > 0):
            # 交点：沿 p→q 按 f 的线性插值
            t = fp / (fp - fq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


# ══════════════════════════════════════════════════════════════════════
#  规模分级：把一个地点的 `size` 变成一个"多重"的整数
# [EN] Weight tiers: turn a place's `size` into an integer "importance"
# ══════════════════════════════════════════════════════════════════════
#: `size` → 权重。**闭集**（模型只会填这几个字，别去猜"中等偏大"）。
# [EN] `size` -> weight. A **closed set** (the model only fills these; do not parse "medium-large")
SIZE_W = {'小': 1, '中': 2, '大': 3, '特大': 4}

#: 城市图里 POI 的分级：地标字大、普通字小
# [EN] POI tiers on the city map: landmarks get larger labels
CITY_FONT = {1: 10, 2: 11, 3: 13, 4: 15}

#: 作者给的**规模** → 城际图等级。只在名字判不出时用（见 `settlement_rank`）。
#: ⚠ 定义已搬到 `worldstyle.SIZE_TO_RANK`（那是唯一一份，小地图也要用）；
#:   这里留个别名是为了不破坏既有 import。
# [EN] Author-declared **size** -> region rank, used only when the name says nothing. ⚠ The
# [EN] definition moved to `worldstyle.SIZE_TO_RANK` (the single copy, shared with the minimap);
# [EN] this alias keeps existing imports working.
SIZE_TO_RANK = WS.SIZE_TO_RANK

#: 城际图的道路**整体缩一档**（相对城市图）。★ 为什么：这个尺度上一根线和城镇圆点
#: 差不多粗就会互相干扰；标准地图在省域尺度也是细线。
#: [EN] The region map draws roads **one notch thinner** than the city map. ★ Why: at this scale a
#: [EN] line as thick as a town dot interferes with it; provincial-scale maps use thin lines too.
REGION_ROAD_SCALE = 0.62

#: 城际图里城镇**行政等级** → 符号大小与字号。按名字判（见 `settlement_rank`）。
# [EN] Administrative rank on the region map -> symbol size and font (see `settlement_rank`)
RANK_FONT = {4: 16, 3: 14, 2: 12, 1: 10}
RANK_R = {4: 7.0, 3: 5.5, 2: 4.0, 1: 2.8}


def settlement_rank(name: str, *, size: str = '', style=None) -> int:
    """这个名字是**什么等级的聚落**：4=都城/州府，3=县城/要塞，2=镇/驿站，1=村/渡/普通。

    ★★★ **本函数只是薄包装**：判法在 `worldstyle.settlement_rank`（那里是唯一一份）。
      为什么搬过去：小地图也要判等级（否则"大图上行距分明的州府与村子，小图上一个大小"），
      而 `minimap` **不能** import `scalemap`（方向反了：`scalemap` 依赖 `minimap`）。
      `worldstyle` 零依赖，两边都能用。
    ★ 保留这个同名函数是为了让旧调用点（判据、`verify_mapscale`）一行都不用改；
      它的 docstring 仍然解释"为什么等级必须按档案取"。
    [EN] What **rank of settlement** this name is: 4 = capital/prefecture, 3 = county seat /
    [EN] fortress, 2 = town / post station, 1 = village / ferry / anything else. ★★★ **A thin
    [EN] wrapper**: the judgement lives in `worldstyle.settlement_rank` (the single implementation).
    [EN] Why it moved: the minimap also needs ranks ("a prefecture and a hamlet at the same size on
    [EN] the minimap"), and `minimap` **cannot** import `scalemap` (wrong direction: `scalemap`
    [EN] depends on `minimap`); `worldstyle` is dependency-free, so both can use it. ★ The same-named
    [EN] function stays so no caller has to change.
    """
    return WS.settlement_rank(name, size=size, style=style)


# ══════════════════════════════════════════════════════════════════════
#  建筑群：院子 / 井台属于那栋楼，不该各算一处建筑
# [EN] Compounds: a courtyard or a well belongs to its building, not its own structure
# ══════════════════════════════════════════════════════════════════════
#: 独立**地物**（不是建筑）：桥、渡口、街市、山、树…
#:
#: ★ 与"建筑"分开的理由（GB/T 20257.1）：房屋按真实轮廓逐个表示，
#:   而桥、渡口、林木是**独立地物**，用各自的符号。混在一起画，
#:   读者会以为"渡口是一栋房子"。
# [EN] Standalone **features** (not buildings): bridge, ferry, market street, hill, trees...
# [EN] ★ Why separate (GB/T 20257.1): buildings are drawn one by one with true outlines, while a
# [EN] bridge, a ferry and woodland are **standalone features** with their own symbols. Mixing them makes
# [EN] the reader think "the ferry is a house".
LANDMARK_SHAPES = ('桥', '渡', '市', '山', '树', '门', '亭', '台')

#: 建筑**底面积**的基准边长（像素，对应"小"）。按 `Place.size` 放大：
#: 小 1.0 / 中 1.25 / 大 1.55 / 特大 1.9。
#:
#: ★★★ 2026-10-27（用户：「所有建筑大小都一样也不太合理」）：
#:   原来所有地物一律画成同半径的圆点，于是"一栋楼"与"一口井"在图上一样大。
#:   制图规范明确要求**保留建筑的大小差异**（USGS《Map Graphics and Generalisation》：
#:   preserve the size differences of buildings），而且更要紧的是比例原理：
#:   建筑物的图上尺寸本应≈占地面积的开方。我们没有真实面积，但 `size` 是作者给的
#:   **相对规模**，用它拉开档次是对的（不是编数字，是把已有等级落到尺寸上）。
# [EN] Base edge length (px, for "small") of a building's **footprint**. Scaled by `Place.size`:
# [EN] 小 1.0 / 中 1.25 / 大 1.55 / 特大 1.9. ★★★ 2026-10-27 (the user: "it is unreasonable that every
# [EN] building is the same size"): everything used to be a dot of one radius, so "a building" and "a
# [EN] well" looked identical. Cartographic generalisation explicitly requires **preserving size
# [EN] differences**, and more importantly the principle of scale: a building's size on paper should be
# [EN] ~sqrt(footprint). We have no true areas, but `size` is the author's **relative scale**, so using it
# [EN] to separate the tiers is right (not inventing numbers -- mapping an existing rank onto a length).
BLDG_BASE = 26.0
# ★ 2026-10-27：档位拉开到 0.85~2.0。原来是 1.0~1.9，实测「特大」只比「小」宽 29%，
#   因为尺寸还要跟地块边长取小 —— 档位本身要更明确，否则被封顶后看不出差别。
# [EN] ★ 2026-10-27: tiers widened to 0.85-2.0 (was 1.0-1.9). Measured, "巨大" came out only 29%
# [EN] wider than "small" because the size is also capped by the parcel edge; the tiers themselves
# [EN] must be explicit or the cap hides them.
SIZE_SCALE_BLDG = {'小': 0.85, '中': 1.25, '大': 1.6, '特大': 2.05}


def compounds(places, style=None) -> tuple:
    """把地点归并成**建筑群**。

    Args:
        places: `Place` 列表。
        style: `worldstyle.Style`（读它的 `见天词` / `陈设词`，不另写一套词表）。

    Returns:
        `(groups, landmarks)`
        * `groups`: `[(主体 Place, [从属 Place…]), …]` —— 一个建筑群一份；
        * `landmarks`: 不属于任何群的**独立地物**（桥/渡/山/树…）。

    ## 为什么必须有这一层（2026-10-27 用户）

    > 「院子 临河楼 后院井台 这几个都是属于临河楼的部分 为何被画到了跨界区的不同建筑里」

    实测那份数据里 `院子` 与 `后院井台` 的 `见天=True`（露天），而 `临河楼` 是楼。
    它们**本来就是一个院落群**：楼 + 它前后的院子。城市图上把三者画成三处建筑，
    读者会以为这是三家邻居 —— 而现实中"楼带着自己的院子"才是最普通的样子。

    ## 判法（三层，全部复用已有词表，不新建）

    1. **见天 = 院落/露天** ⇒ 它属于**最近的建筑主体**（`见天词`：院/天井/庭/井台…）。
       这与 `roomplan` 判"院子不是房间"用的是同一张表，所以两处不会打架。
    2. **建筑主体** = `shape` 在 `LANDMARK_SHAPES` 之外，或名字以后缀字（楼/寺/阁…）结尾。
    3. 其余（桥/渡/市/山/树/门/亭/台）⇒ 独立地物，不并进任何群。

    ★ 判"最近的建筑主体"用欧氏距离，**只在有多个候选时**才分；只有一个主体时
      全都归它（这才是常态：一处院落群）。
    ★ 判不出主体时（整张图只有院子）⇒ 院子自己成一组（不能丢）。
    [EN] Merge places into **compounds**, returning `(groups, landmarks)`. ## Why this layer is
    [EN] required (the user, 2026-10-27): "the courtyard, the building and the well terrace all belong to
    [EN] that building -- why are they drawn as different buildings in different blocks?" Measured, the
    [EN] courtyard and the well terrace have `见天=True` (open sky) while the named place is a building:
    [EN] they are one compound (a building with its yards). Drawing three separate structures makes the
    [EN] reader think they are three neighbours, whereas "a building with its own yard" is the most
    [EN] ordinary thing in reality. ## Rules (three tiers, reusing existing word lists): (1) **open sky =
    [EN] yard** belongs to the **nearest building** (`见天词`: 院/天井/庭/井台..., the same table
    [EN] `roomplan` uses, so the two cannot disagree); (2) a **building** is anything whose `shape` is not
    [EN] in `LANDMARK_SHAPES`, or whose name ends with a building suffix; (3) the rest (bridge / ferry /
    [EN] market / hill / trees / gate / pavilion) are standalone features. ★ "Nearest building" uses
    [EN] Euclidean distance and only matters when there are several candidates; with one building
    [EN] everything belongs to it (the normal case). ★ With no building at all, a yard forms its own group
    [EN] (it must not be dropped).
    """
    ps = [p for p in (places or []) if p is not None]
    st = style or WS.DEFAULT_STYLE if hasattr(WS, 'DEFAULT_STYLE') else style
    sky = tuple(getattr(st, '见天词', ()) or ('院', '天井', '庭', '露台', '晒'))
    fix = tuple(getattr(st, '陈设词', ()) or ())

    def _is_sky(p) -> bool:
        n = str(getattr(p, 'name', '') or '')
        return any(k and k in n for k in sky)

    def _is_landmark(p) -> bool:
        sh = str(getattr(p, 'shape', '') or '')
        return sh in LANDMARK_SHAPES

    def _is_bldg(p) -> bool:
        if _is_landmark(p) or _is_sky(p):
            return False
        n = str(getattr(p, 'name', '') or '')
        sh = str(getattr(p, 'shape', '') or '')
        # 名字带建筑后缀，或 shape 就是"屋" ⇒ 是建筑主体
        if sh in ('屋', '院') and sh != '院':
            return True
        if n.endswith(tuple(ML.BLDG_SUFFIX if hasattr(ML, 'BLDG_SUFFIX') else ('楼',))):
            return True
        return sh == '屋'

    bldgs = [p for p in ps if _is_bldg(p)]
    sky_ps = [p for p in ps if _is_sky(p)]
    marks = [p for p in ps if _is_landmark(p)]
    groups: dict = {id(b): [b] for b in bldgs}
    orphans: list = []

    # ★★★ 2026-10-27：院落分**两轮**归属，不能一律"按最近"。
    #
    #   实测（那份真实数据）：`院子` 到 `临河楼` 是 0.23、到 `兰若寺` 是 0.22 ——
    #   距离几乎一样，按最近判会把它划给兰若寺。而用户的常识是"院子是临河楼的"。
    #   距离在这里本来就不可靠：坐标是 AI 随手给的，`院子` 这种**纯通用名**
    #   （没有专名、没有方位词）根本不携带"我是谁的院"的信息。
    #
    #   可靠的信号有两个，按强弱排序：
    #     ① **方位词**（前/后/内/里/侧/东/西/南/北/左/右）：`后院井台` 里的"后院"
    #        必然相对于某个主体 ⇒ 它到底属于谁可以按距离判（实测 0.17 vs 0.38，很清楚）。
    #     ② **同类已认领**：先认领了"后院井台 ⇒ 临河楼"，再说"院子"——
    #        一处院落群通常只有一套院子，所以纯通用名的院子跟着**已有院子的那组**走。
    #   两轮顺序不能反：先认领方位明确的，纯通用名才有依附对象。
    # [EN] ★★★ 2026-10-27: courtyards are assigned in **two rounds**, not simply "nearest". Measured
    # [EN] on that real dataset: `院子` is 0.23 from `临河楼` and 0.22 from `兰若寺` -- nearly identical,
    # [EN] so a nearest-wins rule hands it to the temple, while the user's common sense says it is the
    # [EN] building's. Distance is unreliable here because the coordinates are model-generated and a
    # [EN] **generic** name like `院子` carries no "whose yard" information at all. Two reliable signals,
    # [EN] strongest first: (1) **positional words** (前/后/内/里/侧/东/西/南/北/左/右) -- "后院" in
    # [EN] `后院井台` is necessarily relative to some building, so distance can settle it (measured 0.17
    # [EN] vs 0.38, unambiguous); (2) **kin already claimed** -- once `后院井台 -> 临河楼` is settled, a
    # [EN] generic `院子` follows the group that already has a yard, since a compound normally has one
    # [EN] yard system. The order cannot be reversed: generic names need an anchor first.
    _POS = ('前', '后', '内', '里', '侧', '东', '西', '南', '北', '左', '右', '上', '下')

    def _claim(target, b) -> None:
        if b not in groups[id(b)]:
            return
        groups[id(b)].append(target)

    def _nearest(cands) -> object | None:
        return cands[0] if len(cands) == 1 else None

    # 第一轮：带方位词的院落 ⇒ 按距离归最近的建筑
    round1 = [s for s in sky_ps
              if any(k in str(getattr(s, 'name', '') or '') for k in _POS)]
    for s in round1:
        if not bldgs:
            orphans.append(s)
            continue
        _claim(s, min(bldgs, key=lambda q: (q.x - s.x) ** 2 + (q.y - s.y) ** 2))

    # 第二轮：纯通用名院落 ⇒ 优先归"已经有院子"的主体，否则按距离
    for s in [x for x in sky_ps if x not in round1]:
        if not bldgs:
            orphans.append(s)
            continue
        with_yard = [b for b in bldgs if any(m in sky_ps for m in groups[id(b)][1:])]
        pool = with_yard or bldgs
        _claim(s, min(pool, key=lambda q: (q.x - s.x) ** 2 + (q.y - s.y) ** 2))
    # 陈设（井/柜台…）同样归最近的主体 —— 它们绝不是独立建筑
    for f in ps:
        if f in sky_ps or f in marks or f in bldgs:
            continue
        if not any(k and k in str(getattr(f, 'name', '') or '') for k in fix):
            continue
        if not bldgs:
            orphans.append(f)
            continue
        b = min(bldgs, key=lambda q: (q.x - f.x) ** 2 + (q.y - f.y) ** 2)
        groups[id(b)].append(f)
    out = [(v[0], v[1:]) for v in groups.values()]
    out += [(o, []) for o in orphans]
    return out, marks


def _footprint_rect(cx: float, cy: float, w: float, h: float) -> list:
    """一个居中的矩形（四个顶点，轴对齐）。**所有建筑轮廓都由它拼出来**。

    ★ 为什么只用轴对齐矩形（GB/T 20257.1：小比例尺"只用正方形和矩形"）：
      用户说「建筑有一些三角和异形建筑 因为在现实中不太常见」——
      那些异形是 Voronoi 多边形。现实中绝大多数房子是矩形或矩形拼成的 L 形，
      三角形（除了极少数坡地建筑）确实罕见。所以轮廓一律由矩形组合。
    [EN] A centred axis-aligned rectangle (four vertices). **Every building outline is built from it.**
    [EN] ★ Why axis-aligned rectangles only (GB/T 20257.1: small scales "use only squares and
    [EN] rectangles"): the user said "some buildings are triangles or odd shapes, which are uncommon in
    [EN] reality" -- those odd shapes were Voronoi polygons. Real buildings are rectangles, or L shapes
    [EN] made of rectangles; triangles are genuinely rare. So outlines are always rectangle composites.
    """
    x0, y0 = cx - w / 2.0, cy - h / 2.0
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]

#: 画"街区"至少要多少处地点。
#:
#: ★★★ 2026-10-27（用户两次纠正，第一次我判错了方向，记在这里）：
#:   第一次报「大地图是一堆长方形叠起来 这个不对的吧」，我判成"不该有街区"，
#:   于是 6 处地点改成不画街区。**这个方向是错的** —— 用户随即纠正：
#:   「**不是不该有街区 而是你的街区画成了一堆长方形堆起来** 不是正确的地图」。
#:
#: 真正的病在两处**画法**，不在街区这个元素：
#:   ① **一处地点切一整块大地块** ⇒ 6 处地点切 6 块，每块都是一整片；
#:      真实的一片城区是**许多小街区**，一处地物落在其中一个街区里，不独占整片地。
#:   ② **块与块边贴边拼满**（Voronoi 的单元共享边界，两条描边直接贴在一起）
#:      ⇒ 界面上就是"砖缝"。真实地图上街区之间是**街道**（有宽度的空隙）。
#:   ⇒ 修法：地块**细分**成 `BLOCK_CELL` 见方的小街区，每块再**内缩** `BLOCK_INSET`
#:     —— 内缩出来的那条带子就是街道。这才是标准地图的画法。
#: 所以阈值只需要"至少要能叫一片城区"：1 处地点谈不上街区，2 处起就画。
# [EN] How many places before drawing **blocks**. ★★★ 2026-10-27 (the user corrected me twice; the
# [EN] first time I read the direction wrong, recorded here): the first report was "the big map is a pile
# [EN] of stacked rectangles, that cannot be right" and I concluded "there should be no blocks", so six
# [EN] places stopped getting them. **That was wrong** -- the user immediately corrected: "**it is not
# [EN] that there should be no blocks; it is that your blocks are drawn as a pile of stacked
# [EN] rectangles** -- that is not a correct map." The real faults are two **drawing** faults, not the
# [EN] element itself: (1) **one place gets one huge parcel**, so six places give six parcels, each a
# [EN] whole swathe; a real urban area is **many small blocks**, and a feature sits inside one of them
# [EN] rather than owning the ground. (2) **Parcels tile edge to edge** (Voronoi cells share borders, so
# [EN] two strokes sit flush) -- that is the "brick joint" look; on a real map, **streets** separate
# [EN] blocks. => Fix: **subdivide** into `BLOCK_CELL` blocks and **inset** each by `BLOCK_INSET`; the
# [EN] gap left behind is the street. That is how a standard map draws it. So the threshold only needs
# [EN] "enough to be an urban area": one place is not a block field, two onward is.
CITY_BLOCKS_MIN = 2

#: 街区**细分**的目标边长（像素）：一片城区要切成许多小块，步进长 60~140px。
#: ⚠ 这与"地块归属"无关：细分出来的小块只是同一片地的更小格子，**不携带额外信息**
#:   （没有名字、没有归属），所以它不是编造 —— 城市街区本来就是均质的地块。
# [EN] Target edge length when **subdividing** blocks (px): an urban area is many small parcels, so step
# [EN] 60-140px. ⚠ Unrelated to "who owns which ground": the small cells carry **no extra
# [EN] information** (no name, no owner), so they are not fabrication -- city blocks are homogeneous.
BLOCK_CELL = 96.0

#: 每个街区面向内缩多少（像素）—— **内缩出来的带子就是街道**。
#: ★ 这是"一堆砖"与"一张地图"的分界：没有这条缝，块与块边贴边，看着就是砖。
# [EN] How far each block is inset (px) -- **the gap left over is the street**. ★ This seam is the
# [EN] difference between "a pile of bricks" and "a map": without it, blocks sit flush and read as bricks.
BLOCK_INSET = 5.0


#: 城市图形态（**闭集**）：`blocks` 街区图 / `area` 导览图（只有 1 处地点时）。
# [EN] City-map modes (**a closed set**): `blocks` block map / `area` guide map (one place only).
CITY_BLOCKS = 'blocks'
CITY_AREA = 'area'


def _city_road_segs(layout, places, pos: dict, net: str) -> list:
    """城市图的**全部路段**：`[(a, b, cls)]`，含棋盘模式的直角折点。

    ★★★ 2026-10-27：抽出来的唯一理由是**街区要被路切开**（用户：「道路穿越建筑了」）。
      切街区必须先知道路在哪，而画路也需要同一份 —— 两处各算一遍必然漂
      （本项目"两处实现必然漂"的头号老坑）。所以路段只在这里定义一次。
    ★ 分级用 `SC.road_class` + `TOP_CITY`（城市尺度的最高级）。写死 4 的话城市图
      永远没有主干道 —— 那条注释原来在绘制循环里，现在跟着逻辑搬过来。
    ★ 棋盘模式走**直角**：街区边是轴对齐的，路斜穿过去就"把街区切开"（自相矛盾）。
    [EN] **All road segments** of the city map: `[(a, b, cls)]`, including the grid mode's right-angle
    [EN] corners. ★★★ 2026-10-27: the only reason this is a separate function is that **blocks must be
    [EN] cut by the roads** (the user: "roads cut through buildings"). Carving needs the roads first and
    [EN] drawing needs the same set -- computing them twice always drifts (this project's number-one
    [EN] pit). So the segments are defined here once. ★ Graded by `SC.road_class` + `TOP_CITY`; a hard 4
    [EN] would mean the city map never produces a trunk road (that note moved here with the logic).
    ★ Grid mode turns at **right angles** (axis-aligned block edges; a diagonal would cut a block).
    """
    out: list = []
    for lk in (getattr(layout, 'links', None) or []):
        a, b = pos.get(lk.get('a')), pos.get(lk.get('b'))
        if not (a and b):
            continue
        cls = SC.road_class(_sizew(lk.get('a'), places), _sizew(lk.get('b'), places),
                            top=SC.TOP_CITY)
        dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
        if net != NET_GRID or dx < 6.0 or dy < 6.0:
            out.append((a, b, cls))
            continue
        corner = (b[0], a[1])
        out.append((a, corner, cls))
        out.append((corner, b, cls))
    return out


def _seg_poly_dist(poly: list[tuple[float, float]], a, b) -> float:
    """一个凸多边形到线段 `a→b` 的**最小距离**（0 表示穿过它）。

    ★ 用"多边形的每个顶点到线段距离"取最小是不够的（长线段可能从多边形中间穿过，
      而所有顶点都很远）。所以两边都算：
        · 顶点到线段的最小距离；· 线段端点到多边形边的最小距离；· 真的相交 ⇒ 0。
    [EN] The **minimum distance** from a convex polygon to the segment `a→b` (0 = it crosses).
    ★ Taking the min over "each vertex to the segment" is not enough (a long segment can pass through
    [EN] the middle while every vertex is far). So both directions: vertex-to-segment, segment-endpoint
    [EN] to polygon edge, and a real intersection => 0.
    """
    if len(poly) < 3:
        return 1e9
    # ① 真的相交（线段与任一条多边形边相交 + 端点落在内部）
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        if _seg_cross(a, b, p, q):
            return 0.0
    if _pt_in_convex(a, poly) or _pt_in_convex(b, poly):
        return 0.0
    # ② 顶点到线段
    best = min(_pt_seg_dist(v, a, b) for v in poly)
    # ③ 端点（这一段对"路从块外侧经过"才起作用，起个保底）
    for e in (a, b):
        for i in range(n):
            p, q = poly[i], poly[(i + 1) % n]
            best = min(best, _pt_seg_dist(e, p, q))
    return best


def _pt_seg_dist(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px_, py_ = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        return math.hypot(px_ - ax, py_ - ay)
    t = max(0.0, min(1.0, ((px_ - ax) * dx + (py_ - ay) * dy) / L2))
    return math.hypot(px_ - (ax + t * dx), py_ - (ay + t * dy))


def _seg_cross(a, b, c, d) -> bool:
    """线段 ab 与 cd 是否**真相交**（跨立实验，不含共线相接）。"""
    def cr(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2 = cr(a, b, c), cr(a, b, d)
    d3, d4 = cr(c, d, a), cr(c, d, b)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _pt_in_convex(p, poly) -> bool:
    """点是否在**凸**多边形内（同侧判定）。"""
    n = len(poly)
    sign = 0
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        c = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        if abs(c) < 1e-9:
            continue
        s = 1 if c > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def _carve_roads(polys: list, segs: list, *, pad: float = 2.0) -> list:
    """把街区**沿道路切开并退让**：`polys − 道路带`。

    Args:
        polys: 街区块（凸多边形列表）。
        segs: `[(a, b, cls)]` 路段。
        pad: 路面之外再留的边距（避免描边压在路上）。

    Returns:
        切开后的凸多边形列表（块数会变多 —— 那正是"街区被路网切开"的样子）。

    ## 做法
    对每条路段，把它**附近**的每一块沿"路中线 ± 半路宽"切成两片：
      · 左片 = 距中线左侧 ≥ r 的部分；右片同理 —— 用 `_clip_half` 一次裁出
        （`s = a + n*(r+1)`、`o = a + n*(r-1)` 的垂直平分线正好是"距中线 r"的那条平行线）。
      · 两片都**退让了 r**，所以中间的 `2r` 宽空带就是路面。
    ★ 只切**离路足够近**的块（`dist < r*4`）：远处的块完全不受影响，
      否则整张图会被切成碎片（每条路的无限延长线都切一遍是错的）。
    ★ 半路宽 `r` 取该路段自己的 `ROAD_SPEC` 外宽/2 —— 主干道让得宽、支路让得窄，
      与画出来的路宽**同一份参数**（否则"让位"与"路面"宽度不一致，缝会露出来）。
    ★ 递归：一个块可能被多条路穿过，所以对每条路都把当前所有碎片再过一遍。
    [EN] **Cut the blocks along the roads and push them back**: `polys - road band`. Approach: for
    [EN] each segment, split every **nearby** block along "centreline +/- half width" into two pieces,
    [EN] each already pushed back by r (the bisector of `a + n*(r+1)` and `a + n*(r-1)` is exactly the
    [EN] line "distance r from the centreline"), so the `2r` band left in between is the road surface.
    [EN] ★ Only blocks **close enough** are cut (`dist < r*4`); otherwise the whole map shatters (cutting
    [EN] with every road's infinite extension is wrong). ★ `r` is half the segment's own `ROAD_SPEC`
    [EN] width -- a trunk gives way more than a lane, from the **same parameters** used to draw it (or
    [EN] the gap would not match the surface). ★ Recursive: one block may be crossed by several roads.
    """
    out = [list(p) for p in polys if len(p) >= 3]
    for (a, b, cls) in segs:
        outer, _inner, _centre = SC.ROAD_SPEC.get(cls, SC.ROAD_SPEC[SC.RC_LOCAL])
        r = outer / 2.0 + pad
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L <= 1e-6:
            continue
        nx, ny = -dy / L, dx / L            # 中线法向
        nxt: list = []
        for poly in out:
            if _seg_poly_dist(poly, a, b) > r * 4.0:
                nxt.append(poly)            # 离得远，不动
                continue
            # 左片：距中线 ≥ +r；右片：≤ -r。两片各自已经退让，中间那条带就是路。
            # [EN] Left piece: >= +r from the centreline; right piece: <= -r. Both already pushed
            # [EN] back, and the band between them is the road.
            lp = _clip_half(poly, a[0] + nx * (r + 1.0), a[1] + ny * (r + 1.0),
                            a[0] + nx * (r - 1.0), a[1] + ny * (r - 1.0))
            rp = _clip_half(poly, a[0] - nx * (r + 1.0), a[1] - ny * (r + 1.0),
                            a[0] - nx * (r - 1.0), a[1] - ny * (r - 1.0))
            for piece in (lp, rp):
                if len(piece) >= 3:
                    nxt.append(piece)
        out = nxt
    return out


def _inset_convex(poly: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    """把**凸**多边形每条边向内侧平移 `d`，取新多边形的交点（即"内缩"）。

    ★ 为什么需要它（2026-10-27）：街区若按 Voronoi 单元原样画，相邻单元**共享同一条边界**，
      两条描边直接贴在一起 —— 屏幕上就是"一堆砖的砖缝"。
      内缩 `d` 之后，块与块之间留下 `2d` 宽的**空隙**，那空隙就是街道。
      这是标准地图的画法：街区面（parcel）永远比道路中线小一圈。
    ★ 只用凸多边形：Voronoi 单元是半平面的交集 ⇒ 一定是凸的；细分的格子也是凸的。
      非凸输入会得到错误结果 —— 所以调用方必须是凸的（`voronoi` / `_split_rect` 都保证）。
    ★ 内缩过头（d 超过内切圆半径）会让多边形退化 ⇒ 返回空表，调用方跳过这一块
      （比画出一块翻转的怪形状好）。
    [EN] Move every edge of a **convex** polygon inward by `d` and take the intersections ("inset").
    ★ Why (2026-10-27): drawing Voronoi cells as-is means neighbours **share an edge**, so two strokes
    sit flush -- the "brick joint" look. Insetting by `d` leaves a `2d` **gap**, and that gap is the
    street. This is how standard maps draw it: a parcel is always smaller than the road centreline.
    ★ Convex only: Voronoi cells are intersections of half-planes, hence convex, and subdivided cells
    are too. Non-convex input yields wrong output, so callers must pass convex polygons.
    ★ Over-insetting (beyond the inradius) degenerates the polygon => return empty and let the caller
    skip the cell (better than drawing a flipped shape).
    """
    if len(poly) < 3 or d <= 0:
        return list(poly)
    out = list(poly)
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        L = math.hypot(ex, ey)
        if L <= 1e-9:
            continue
        # 内法向：按"多边形顶点顺序"取一侧；用重心判定哪一侧是内部
        nx, ny = -ey / L, ex / L
        cx = sum(p[0] for p in poly) / n
        cy = sum(p[1] for p in poly) / n
        if (cx - ax) * nx + (cy - ay) * ny < 0:
            nx, ny = -nx, -ny
        # 把这条边沿内法向推 d，保留"推进后仍在内侧"的一半
        px, py = ax + nx * d, ay + ny * d
        out = _clip_half(out, px + nx, py + ny, px - nx, py - ny)
        if len(out) < 3:
            return []
    return out


def _vary(x0: float, x1: float, cell: float, seed: int = 0) -> list:
    """把 `[x0, x1]` 按 `cell` 切成**宽度不一**的段（确定性，可复现）。

    ★★★ 2026-10-27（用户：「所有建筑大小都一样也不太合理」）：
      原来 `_split_rect` 是把矩形**均分**成边长 ~96px 的格子，于是图上几十块街区
      尺寸完全一致 —— 看起来像地砖，不像城市。真实街区的临街面宽度本来就不齐
      （老城 20~60m、新区 80~200m，掺在一起）。

    ★ 为什么用"确定性抖动"而不是随机：地图必须**同一份数据永远同一张图**
      （这是本项目"延续性靠纯函数"的纪律）。所以抖动来自 `(索引 × 质数) % 质数`
      —— 看起来无序、但完全可复现。

    ★ 抖动幅度取 0.62~1.38 倍：再大就会出现"一条细缝 + 一块巨无霸"，
      比均分更假（GB/T 20257.1 的图面负载要求）。
    [EN] Cut `[x0, x1]` into segments of **unequal width** by `cell` (deterministic, reproducible).
    ★★★ 2026-10-27 (the user: "it is unreasonable that every building is the same size"): `_split_rect`
    [EN] used to divide **evenly** into ~96px cells, so dozens of parcels came out identical -- like floor
    [EN] tiles, not a city. Real street frontages vary (old town 20-60 m, new districts 80-200 m, mixed).
    ★ Why deterministic jitter instead of randomness: one dataset must always yield one map (this
    [EN] project's "continuity via pure functions" rule), so the wobble comes from `(index * prime) %
    [EN] prime` -- disordered in appearance, fully reproducible. ★ The amplitude is 0.62-1.38x; beyond
    [EN] that you get "one hairline slot plus one giant block", which is more fake than an even grid
    [EN] (GB/T 20257.1's map-load requirement).
    """
    span = float(x1) - float(x0)
    if span <= 0:
        return []
    n = max(1, int(round(span / max(8.0, cell))))
    weights = []
    for i in range(n):
        # 三个互质步长叠起来，避免出现周期性花纹
        h = (i * 37 + seed * 11) % 23
        weights.append(0.62 + 0.76 * (h / 22.0))
    tot = sum(weights)
    out = []
    cur = float(x0)
    for w in weights:
        nxt = cur + span * (w / tot)
        out.append((cur, nxt))
        cur = nxt
    out[-1] = (out[-1][0], float(x1))
    return out


def _split_rect(x0: float, y0: float, x1: float, y1: float,
                cell: float) -> list[tuple[float, float, float, float]]:
    """把一个矩形切成**大小不一**的小格（返回 `(x0,y0,x1,y1)` 列表）。

    ★ 为什么"细分"不算编造：街区是**均质的地块**，没有名字、没有归属，
      真实城市地图上就是一片片小格子；把它画成"一块特大地"才是失真。
    ★ 2026-10-27：从"均分"改成 `_vary` 的**不等分** —— 用户说大小一样不合理。
    ★ 边界上的块不补齐（城市边缘本来就不整齐）。
    [EN] Cut a rectangle into **unequal** cells. ★ Why subdividing is not fabrication: blocks are
    [EN] **homogeneous parcels** -- no names, no owners -- and a real city map shows many small cells;
    [EN] "one giant parcel" is the distortion. ★ 2026-10-27: from even division to `_vary`'s
    [EN] **unequal** division, because the user said identical sizes are unreasonable. ★ Edge cells are
    [EN] not padded (a city edge is naturally ragged).
    """
    if x1 - x0 < 8.0 or y1 - y0 < 8.0:
        return []
    xs = _vary(x0, x1, cell, seed=1)
    ys = _vary(y0, y1, cell, seed=2)
    return [(a, b, c, d) for (a, c) in xs for (b, d) in ys]



def city_blocks(pos: dict, box: tuple, *, net: str = 'organic',
                cell: float | None = None) -> list[list[tuple[float, float]]]:
    """城市图上的**街区面**：先按路网形态切归属，再**细分**、再**内缩**。

    Args:
        pos: `{名字: (x, y)}` 像素坐标。
        box: 绘图区 `(x0, y0, x1, y1)`。
        net: 路网形态（`NET_GRID` / `NET_RADIAL` / `NET_ORGANIC`）。
        cell: 细分步进；不给就用 `BLOCK_CELL`。

    Returns:
        一组**内缩后**的凸多边形 —— 直接画就是"一块块被街道隔开的街区"。

    ★★★ 2026-10-27：这个函数的全部意义是**修"一堆长方形堆起来"**（用户两次报）。
      修法两条，各自对应一个症状：
        ① **细分**（`_split_rect`）：一处地点不再独占一整片地。6 处地点切成几十个小块，
           视觉上才是"一片城区"，而不是"六块砖"。
        ② **内缩**（`_inset_convex`）：块与块之间留 `2×BLOCK_INSET` 的空隙 —— 那空隙
           就是街道。没有它，Voronoi 的共享边界会让两条描边贴在一起，看着像砖缝。
      ⚠ 细分**不引入新信息**：小格子没有名字、没有归属，只是把同一片地画细
        （真实城市地图就是这么画的）。所以这不违反"不编造"。
    [EN] The **block parcels** of a city map: assign by network form, then **subdivide**, then
    [EN] **inset**. ★★★ 2026-10-27: the whole point of this function is to fix "a pile of stacked
    [EN] rectangles" (reported twice). Two fixes, one symptom each: (1) **subdivision** -- a place no
    [EN] longer owns a whole swathe; six places become dozens of small cells, which reads as "an urban
    [EN] area" instead of "six bricks". (2) **inset** -- a `2 x BLOCK_INSET` gap between cells, and that
    [EN] gap is the street; without it the shared Voronoi edges put two strokes flush and it looks like
    [EN] brick joints. ⚠ Subdivision **introduces no information**: the cells have no name and no owner,
    [EN] they only draw the same ground finer (which is what real city maps do), so it does not violate
    [EN] "never fabricate".
    """
    step = float(cell or BLOCK_CELL)
    x0, y0, x1, y1 = (float(v) for v in box)
    if len(pos) < 2:
        return []
    if net == NET_GRID:
        cells = grid_cells(pos, box)
    elif net == NET_RADIAL:
        cells = radial_cells(pos, box)
    else:
        cells = list(voronoi([(nm, p[0], p[1]) for nm, p in pos.items()], box).values())
    sub: list[list[tuple[float, float]]] = []
    for poly in cells:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
        for (cx0, cy0, cx1, cy1) in _split_rect(bx0, by0, bx1, by1, step):
            piece = _clip_rect(poly, cx0, cy0, cx1, cy1)
            if len(piece) >= 3:
                sub.append(piece)
    out: list[list[tuple[float, float]]] = []
    for poly in sub:
        got = _inset_convex(poly, BLOCK_INSET)
        if len(got) >= 3:
            out.append(got)
    return _drop_slivers(out)

# ══════════════════════════════════════════════════════════════════════
#  街区里的**无名建筑体量**（城市尺度）
# [EN] The **anonymous building massing** inside the blocks (city scale)
# ══════════════════════════════════════════════════════════════════════

#: 一排建筑的进深（含排与排之间的空隙），px
#: [EN] Depth of one row of buildings (including the gap between rows), px
LOT_ROW = 12.0
#: 一栋的临街面宽（含栋与栋之间的空隙），px
#: [EN] Street frontage of one building (including the gap between neighbours), px
LOT_W = 21.0
#: 栋与栋之间的空隙（巷道 / 院墙缝），px
#: [EN] Gap between neighbouring buildings (an alley / party-wall slot), px
LOT_GAP = 2.6
#: 街区边界到建筑的距离（人行道 / 前院），px
#: [EN] Distance from the block edge to the buildings (pavement / front yard), px
LOT_SETBACK = 3.2
#: 小于这个尺寸就不画建筑（GB/T 20257.1 的"综合取舍"）
#: [EN] Below this size no building is drawn (GB/T 20257.1 "generalisation"), px
LOT_MIN = 5.5

#: 地块内缩（px）。极小：街宽已经由**街距**体现，这里只是让街沿有一条细缝。
#: ⚠ 原来用 `BLOCK_INSET = 5.0`（Voronoi 时代为了把共享边界拉开）；
#:   现在地块是街围出来的，内缩 5px 会让街区缩成一小块、四周留白像空地。
# [EN] Parcel inset (px). Tiny: street width now comes from the **spacing**, and this only leaves a
# [EN] hairline along the kerb. ⚠ It used to be `BLOCK_INSET = 5.0` (to pull shared Voronoi edges
# [EN] apart); parcels are now enclosed by streets, and 5px would shrink them into empty ground.
LOT_INSET = 1.5
#: 体量的填充强度：比**主体楼**（0.72）浅得多，比街区底纹（0.06）深
#: [EN] Massing fill strength: far lighter than a **main building** (0.72), darker than block tint (0.06)
MASS_FILL = 0.32

# ══════════════════════════════════════════════════════════════════════
#  路网：城市的**骨架**（与地点无关）
# [EN] The street network: the town's **skeleton**, independent of the places
# ══════════════════════════════════════════════════════════════════════

#: 街网的目标间距（px）—— 决定"一片城区有多少条街"
#: [EN] Target street spacing (px) -- how many streets a stretch of town has
SN_TARGET = 112.0

#: 街网的整体**方位角**（弧度）。真实城镇很少正南北。
#: `grid` 也有一点偏角：中式棋盘城是正交的，但**整城有方位**；
#: 若一律 0°，图看起来像 CAD 图，不像地图（用户：「太横平竖直」）。
#: [EN] The whole network's **bearing** (radians). Real towns are rarely due north.
#: [EN] Even `grid` gets a small one: a Chinese chessboard city is orthogonal, but the *town* has a
#: [EN] bearing; at exactly 0 the drawing looks like a CAD file, not a map (the user: "too rectilinear").
# ⚠ 用**字符串字面量**当键：这张表在模块加载时就要建好，而 `NET_*` 常量定义在文件更后面
#   （`city_mode` 那一节）—— 引用它们会 `NameError`。值必须与那几个常量一致。
# [EN] ⚠ String literals as keys: this table is built at import time while the `NET_*` constants
# [EN] are defined further down (the `city_mode` section) -- referring to them raises NameError.
SN_ANGLE = {'grid': 0.048, 'organic': 0.105, 'radial': 0.02}

#: 胡同/巷的宽度（px）。巷**不通到城外**，只在地块内部联系两侧院落。
#: [EN] Alley width (px). An alley does not reach outside; it links the yards inside one parcel.
SN_LANE_W = 3.4

#: `organic` 网格角点的抖动幅度（px）。自然生长的城镇，街道方向本来就不一致。
#: ⚠ `grid` 用 0：棋盘城就是要正。
# [EN] Vertex jitter for `organic` (px). In an organic town the street directions genuinely disagree.
# [EN] ⚠ `grid` uses 0: a chessboard city is meant to be orthogonal.
SN_JITTER = 7.5

#: **地块的最小面积（px²）**。小于它的碎块不画 —— GB/T 20257.1 的"综合取舍"：
#: 被道路/图廓切出来的几十像素小三角，留着只会让图上多一片碎渣。
#: ⚠ 只此一处定义：`streetnet` 的过滤与判据都用它（两处各写一个阈值必然漂）。
# [EN] **Minimum parcel area (px^2)**. Smaller fragments are not drawn -- GB/T 20257.1's
# [EN] "generalisation": tiny triangles cut out by roads or the neat line only add debris.
# [EN] ⚠ Defined once: both `streetnet`'s filter and the criterion use it (two thresholds always drift).
LOT_MIN_AREA = 380.0

#: 地块长边超过它才值得开一条巷（否则地块太窄，开了就没院子）
#: [EN] A parcel's long side must exceed this before an alley is cut (else no yard is left)
SN_LANE_MIN = 96.0

#: 街网里"每第几条"升级为主干道（其余次干道）。真实城镇的主干道是少数。
#: [EN] Every n-th line is promoted to trunk (the rest are secondary). Real towns have few arterials.
SN_TRUNK_EVERY = 3


def _clip_seg(a: tuple, b: tuple, box: tuple) -> tuple | None:
    """把线段 `a→b` 裁到矩形 `box` 内（Liang-Barsky）。完全在外返回 `None`。

    ★ 为什么必须裁：街网按**外接圆**铺（保证旋转后四角也盖住），于是每条街的端点都在
      图廓外。不裁的话图元坐标会跑到画布外（实测 y=-34 / 776，画布高 600）——
      用户报过"地图出了对话框边界"。
    ★ 为什么不用"把端点夹到边界"：夹端点会改变线段斜率，斜街会被掰弯。
      Liang-Barsky 精确求与图廓的交点，长度变了但方向不变。
    [EN] Clip segment `a->b` to rectangle `box` (Liang-Barsky); `None` when fully outside.
    ★ Why clipping is required: the network is laid out on a **circumscribed radius** (so the rotated
    [EN] corners are covered), which puts every street's endpoints outside the neat line. Unclipped, the
    [EN] primitives land off-canvas (measured y=-34/776 on a 600-tall canvas) -- the user had reported
    [EN] "the map goes outside the dialog". ★ Why not clamp the endpoints: clamping changes the slope and
    [EN] bends a slanted street; Liang-Barsky finds the exact intersections, so only the length changes.
    """
    x0, y0, x1, y1 = box
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    if t0 > t1:
        return None
    return ((a[0] + dx * t0, a[1] + dy * t0), (a[0] + dx * t1, a[1] + dy * t1))


def _outside(quad: list, x0: float, y0: float, x1: float, y1: float) -> bool:
    """四边形是否有顶点在图廓外。 English: whether any quad vertex lies outside the neat line."""
    return any(p[0] < x0 or p[0] > x1 or p[1] < y0 or p[1] > y1 for p in quad)


def _orient(poly: list) -> list:
    """把多边形统一成**逆时针**（裁剪函数要求固定绕向，否则会裁成空）。

    ★ 2026-10-27 实测：`radial` 的地块全部消失（出图 0 块）。原因不是几何算错，而是
      扇形四边形的绕向与 `_clip_rect` 假设的相反 —— 一裁就空，且**不报错**。
      网格形态的图没暴露这一点，因为它们的地块大多在图内、根本不走裁剪分支。
    [EN] Normalise a polygon to **counter-clockwise** (the clipper requires a fixed winding or it
    [EN] returns nothing). ★ Measured 2026-10-27: every `radial` parcel vanished (0 on the map). The
    [EN] geometry was fine -- the sector quads were wound the other way than `_clip_rect` expects, so
    [EN] clipping produced nothing, **silently**. Grid maps never exposed it because their parcels are
    [EN] mostly inside the frame and never reach the clip branch.
    """
    a = 0.0
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        a += ax * by - bx * ay
    return list(poly) if a >= 0 else list(reversed(poly))


def pt_in_poly(pt: tuple, poly: list, tol: float = 0.0) -> bool:
    """点是否在**任意**（含凹）多边形内（射线法）。

    ★ 为什么需要它：地块被图廓裁过之后可能是 L 形（凹）。`_pt_in_convex` 对凹多边形
      会把**合法**的点判成在外（它只认凸包），判据因此误报"建筑跑出街区"（实测 136 栋）。
    [EN] Whether a point is inside an **arbitrary** (including concave) polygon, by ray casting.
    ★ Why: after the neat-line clip a parcel may be L-shaped (concave), and `_pt_in_convex` rejects
    [EN] legitimate points there (it only knows the convex hull) -- the criterion then reported 136
    [EN] buildings "outside their block".
    """
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if (ay > y) != (by > y):
            t = (y - ay) / (by - ay) if abs(by - ay) > 1e-12 else 0.0
            if x < ax + t * (bx - ax):
                inside = not inside
    if inside or tol <= 0:
        return inside
    # ★ 贴边容差：建筑沿街排、只退 `LOT_SETBACK`，角点常常离地块边不到 1px，
    #   射线法在那种距离上会因浮点落到边外（实测一栋角点离边 0.75px 被判"在外"）。
    #   制图上"贴着街沿"本来就是合法的，所以 `tol` 之内算在内。
    # [EN] ★ Edge tolerance: buildings front the street with only `LOT_SETBACK`, so a corner often sits
    # [EN] within 1px of the parcel edge, where ray casting flips on floating point (measured: a corner
    # [EN] 0.75px from the edge read as "outside"). Fronting the kerb is legitimate on a map, so
    # [EN] anything within `tol` counts as inside.
    for i in range(n):
        if _pt_seg_dist(pt, poly[i], poly[(i + 1) % n]) <= tol:
            return True
    return False


def _poly_area(poly: list) -> float:
    """多边形面积（绝对值）。 English: polygon area (absolute)."""
    a = 0.0
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        a += ax * by - bx * ay
    return abs(a) / 2.0


def _lines(lo: float, hi: float, step: float, seed: int = 0, *,
           even: bool = False) -> list:
    """`[lo, hi]` 内的**不等距**街网线位置（含两端）。

    ★ 为什么不等距：真实城镇的街距本来就不齐（老城 30~60m、新区 80~200m 混在一起）。
      等距会切出一模一样的方块 —— 那就是用户说的"像地砖"。
    ★ 为什么确定：地图必须同一份数据永远同一张图（本项目"延续性靠纯函数"）。
      抖动来自 `(索引 × 质数) % 质数`，看起来无序、完全可复现。
    [EN] **Unequal** street positions in `[lo, hi]` (both ends included). ★ Why unequal: real street
    [EN] spacing is uneven (old town 30-60 m, new districts 80-200 m mixed); an even grid yields
    [EN] identical squares, i.e. "floor tiles". ★ Why deterministic: one dataset must always produce one
    [EN] map, so the wobble comes from `(index * prime) % prime` -- disordered, fully reproducible.
    """
    span = float(hi) - float(lo)
    if span <= 0:
        return []
    n = max(1, int(round(span / max(20.0, float(step)))))
    if even:
        return [float(lo) + span * (i / n) for i in range(n + 1)]
    # ★ 2026-10-27：幅度从 0.78~1.22 拉到 **0.62~1.38**。原来那档的变异系数只有 7%，
    #   跟棋盘的 5.9% 几乎分不开（判据量出来就是"两种形态一样规整"）。
    #   真实的自然城镇街距本来就参差：老城 30~60 m 与新区 120 m 混在一起。
    # [EN] ★ 2026-10-27: widened from 0.78-1.22 to **0.62-1.38**. The old range had a 7% coefficient of
    # [EN] variation, indistinguishable from the grid's 5.9% (the criterion measured "both forms equally
    # [EN] regular"). Real organic towns genuinely mix 30-60 m lanes with 120 m streets.
    weights = [0.62 + 0.76 * (((i * 37 + seed * 13) % 19) / 18.0) for i in range(n)]
    tot = sum(weights) or 1.0
    out = [float(lo)]
    cur = float(lo)
    for w in weights:
        cur += span * (w / tot)
        out.append(cur)
    out[-1] = float(hi)
    return out


def streetnet(box: tuple, *, net: str = 'organic', seed: int | None = None,
              target: float | None = None) -> dict:
    """生成一张**路网**与它围出的**地块**（城市尺度的骨架）。

    Args:
        box: 绘图区 `(x0, y0, x1, y1)`。
        net: 路网形态（`'grid'` 正交棋盘 / `'organic'` 街巷 / `'radial'` 放射环）。
             ⚠ 默认值是**字符串**而不是 `NET_ORGANIC` 常量：默认参数在函数定义时就求值，
             而那几个常量定义在本文件更后面（`NameError`）。
        seed: 抖动种子；**不给（None）就由 `box` 算** —— 同一片区域永远同一张网，
             不同的城区各有各的抖动。
             ⚠ 默认值必须是 `None` 而不是 `0`：写成 `0` 的话下面那句
             `if seed is None` 永不成立，"按位置算种子"是**死代码**，
             所有城市会共用同一套抖动（实测就是这么发现的）。
        target: 街距；不给用 `SN_TARGET`。

    Returns:
        `{'roads': [(pts, cls)], 'lots': [quad], 'lanes': [(pts, cls)], 'bearing': th}`
        `pts` 是折线点列（2 点即一段），`cls` 是 `scale.RC_*` 分级；
        `quad` 是**地块**（4 点，绕行顺序一致）。

    ## 为什么要有这个函数（2026-10-27 用户的第四条重话）

    > 「其中的道路正常画 而不是直接连接几个目标建筑 真正地图中 是不会出现这样的直连道路的」

    原来的路是 `layout.links` 的**两地点连线** —— 那表达的是"这两处之间有路可走"
    （一个**可达关系**），而地图上的路是**城市骨架**：它先于任何一处建筑存在，
    建筑沿它落座。把可达关系当路画，必然出现"从 A 拉到 B"的斜直线、
    且所有路都汇聚到几个目标建筑上（主角楼变成路网枢纽）——
    真实城市里没有这种事：**任何一栋楼（包括主角住的）都只是街上的一户**。

    ⇒ 现在路网**完全不看地点**：由街距、方位角、形态决定。地点只决定"哪块地块上
      画一栋有名字的要地"，不影响一条街的走向或位置。

    ## 三种形态（对应 `worldstyle.Style.路网`）

    | 形态 | 地图上的样子 | 依据 |
    |---|---|---|
    | `grid` 棋盘 | 正交街道，整城有方位角，主干道每 3 条 | 唐长安"九条南北街 + 十二条东西街"、明清北京街巷 |
    | `organic` 街巷 | 不等距、可变向、多死胡同、地块缺角 | 中世纪欧洲城镇 2~4m 窄巷、放射+环 + 死胡同 |
    | `radial` 放射 | 从城心放射的主街 + 同心环街 | 欧洲放射同心式、环形空间站 |

    ## 巷（`lanes`）

    地块长边够长时，沿**长边方向**开一条窄巷，把地块分成两条临街的院落带。
    这就是"胡同"：它**不通到城外**，只解决地块内部的进出。
    [EN] Generate a **street network** and the parcels it encloses (the town-scale skeleton).
    [EN] ## Why this function exists (the user's fourth hard note, 2026-10-27): "draw the roads
    [EN] normally instead of connecting a few target buildings; a real map has no such direct links".
    [EN] The old roads WERE the `layout.links` between two places -- a **reachability relation** -- while
    [EN] a road on a map is the town's **skeleton**: it exists before any building, and buildings sit
    [EN] along it. Drawing reachability as roads necessarily produces "A to B" diagonals converging on
    [EN] a few target buildings (the protagonist's house becomes a network hub), which no real town has:
    [EN] **every building, including the protagonist's, is one household on a street**. => The network
    [EN] now ignores places entirely (spacing, bearing, form decide it); a place only decides "which
    [EN] parcel carries a named building", never a street's direction or position. ## Three forms
    [EN] (`worldstyle.Style.路网`): grid = orthogonal, whole-town bearing, every 3rd line a trunk
    [EN] (Tang Chang'an's nine north-south + twelve east-west streets, Ming-Qing Beijing's lanes);
    [EN] organic = uneven, varying direction, many dead ends, parcels with cut corners (medieval
    [EN] European towns, 2-4 m lanes, radial + ring + cul-de-sacs); radial = arterials from the centre
    [EN] plus ring streets (European radiocentric plans, ring stations). ## Alleys: when a parcel's long
    [EN] side is long enough, a narrow alley is cut **along that long side**, splitting it into two
    [EN] street-fronting yard bands -- that is a hutong, and it never reaches outside the parcel.
    """
    x0, y0, x1, y1 = (float(v) for v in box)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    th = SN_ANGLE.get(net, SN_ANGLE[NET_ORGANIC])
    step = float(target or SN_TARGET)
    # 覆盖半径：旋转之后仍要盖住整个绘图区（否则四角会缺街区）
    # [EN] Coverage radius: must still cover the whole drawing area after rotation
    rad = math.hypot(x1 - x0, y1 - y0) / 2.0 + 12.0
    if seed is None:
        seed = int(abs(round(x0 * 3.0 + y0 * 7.0))) % 89

    def P(u: float, v: float) -> tuple:
        """u-v → 屏幕。`radial` 用极坐标（u=半径、v=角度），于是街网是环 + 放射。"""
        if net == NET_RADIAL:
            a = th + v
            return (cx + u * math.cos(a), cy + u * math.sin(a))
        c, s_ = math.cos(th), math.sin(th)
        return (cx + u * c - v * s_, cy + u * s_ + v * c)

    even = (net == NET_GRID)
    if net == NET_RADIAL:
        us = _lines(rad * 0.16, rad, step * 1.05, seed + 1)
        # 放射街：角度上均匀分 12~18 条（不是"不等距"，角度本来就要匀）
        # ⚠ 环形街用**折线**近似圆弧，每段都会向圆心凹进 `r(1-cos(θ/2))`（弓高）。
        #   段太粗时弓高超过街宽，环街就压到地块上（实测 14 段 @ r=300 时弓高 7.4px）。
        #   这里把段加密到 24（约 15°，弓高约 2.6px），并在内缩量里留出补偿。
        # [EN] ⚠ Ring streets are **polylines** approximating arcs, each sagging toward the centre by
        # [EN] `r(1-cos(θ/2))`. With coarse segments that sag exceeds the street width and the ring cuts
        # [EN] into parcels (measured 7.4px sag at 14 segments, r=300). Densify to 24 (~15°, ~2.6px sag)
        # [EN] and allow for it in the inset.
        nv = 24
        vs = [math.pi * 2.0 * i / nv for i in range(nv)]
    else:
        us = _lines(-rad, rad, step, seed + 1, even=even)
        vs = _lines(-rad, rad, step * 0.9, seed + 2, even=even)

    # ★★★ 2026-10-27（实测抓到的）：地块边界**就在街道中线上**，所以每块地必须按
    #   它那四条边所邻街道的**半宽**退回，否则建筑会压在路上（实测 398 栋压路）。
    #   原来只内缩 1.5px —— 那是"街沿细缝"，不是"让出路面"。
    # [EN] ★★★ 2026-10-27 (measured): a parcel's edge **is the street centre line**, so each parcel
    # [EN] must retreat by the **half-width of the street it borders**; otherwise buildings sit on the
    # [EN] road (398 measured). The old 1.5px was a kerb hairline, not "give way to the carriageway".
    def _hw(cls: str) -> float:
        # +1.5 的余量：抖动过的地块边不是严格垂直/平行，法向内缩后短边会差一点
        # [EN] +1.5 margin: a jittered parcel edge is not exactly perpendicular, so after a normal
        # [EN] inset the short side ends up slightly closer
        return SC.ROAD_SPEC[cls][0] / 2.0 + 1.5

    _jit = {'grid': 0.0, 'organic': SN_JITTER, 'radial': SN_JITTER * 0.35}.get(net, SN_JITTER)

    def _V(i: int, j: int) -> tuple:
        """网格角点的**屏幕坐标**（带确定性抖动）。同一 `(i,j)` 永远同一个点 ⇒ 相邻地块共享它。

        ⚠ 必须过 `P()`：抖动是加在 **u-v** 上的，漏掉映射就等于把 u-v 当屏幕坐标用
          —— 地块会全部跑到图外（实测地块数从 49 掉到 21，而且图上只剩中间几块）。
        [EN] The grid vertex in **screen space** (with deterministic jitter); the same `(i,j)` always
        [EN] gives the same point, so neighbouring parcels share it. ⚠ It must go through `P()`: the
        [EN] jitter is added in **u-v** space, and skipping the mapping treats u-v as screen coordinates
        [EN] -- parcels then fall outside the frame (measured: 49 -> 21, only a few left in the middle).
        """
        if not _jit:
            return P(us[i], vs[j])
        h1 = ((i * 37 + j * 91 + seed * 13) % 23) / 22.0 - 0.5
        h2 = ((i * 71 + j * 17 + seed * 29) % 19) / 18.0 - 0.5
        if net == NET_RADIAL:
            # ⚠ 极坐标里 `vs` 是**弧度**，直接加 7.5px 的抖动等于转 400 多度
            #   （实测地块全乱、186 块压路）。角度抖动必须按 `px / r` 换算。
            # [EN] ⚠ In polar coordinates `vs` is in **radians**, so adding a 7.5px jitter rotates by
            # [EN] hundreds of degrees (measured: parcels scrambled, 186 blocks on roads). The angular
            # [EN] jitter must be converted as `px / r`.
            dth = _jit / max(1.0, abs(us[i]))
            return P(us[i] + h1 * 2.0 * _jit, vs[j] + h2 * 2.0 * dth)
        return P(us[i] + h1 * 2.0 * _jit, vs[j] + h2 * 2.0 * _jit)

    u_cls = [(SC.RC_TRUNK if k % SN_TRUNK_EVERY == 0 else SC.RC_MAIN) for k in range(len(us))]
    v_cls = [(SC.RC_TRUNK if k % (SN_TRUNK_EVERY + 1) == 0 else SC.RC_MAIN)
             for k in range(len(vs))]

    # ★★★ 2026-10-27：街道与地块**共用同一组角点**（`_V`）。
    #   第一版只抖了地块角点、街道还是直线 ⇒ 抖过的那条边越过了街道中线，
    #   于是"每块街区都被路穿过"（实测 72/72）。共享角点之后，街道是**微弯的折线**
    #   （自然生长的城镇本来就是这样），地块永远落在街道围出的面里。
    #   ⚠ `grid` 抖动为 0 ⇒ 折线退化成直线，仍是正交棋盘。
    # [EN] ★★★ 2026-10-27: streets and parcels **share the same vertices** (`_V`). The first version
    # [EN] jittered only the parcel corners while the streets stayed straight, so a wobbled edge crossed
    # [EN] the street centre line and **every block was crossed by a road** (measured 72/72). Sharing the
    # [EN] vertices makes each street a **slightly bent polyline** (which is what an organic town looks
    # [EN] like) and guarantees parcels lie inside the faces the streets enclose. ⚠ With `grid` the
    # [EN] jitter is 0, so the polyline degenerates to a straight line and stays orthogonal.
    roads: list = []
    if net == NET_RADIAL:
        for k in range(len(us)):
            roads.append(([_V(k, j) for j in range(len(vs))] + [_V(k, 0)], u_cls[k]))
        for k in range(len(vs)):
            roads.append(([_V(i, k) for i in range(len(us))], v_cls[k]))
    else:
        for k in range(len(us)):
            roads.append(([_V(k, j) for j in range(len(vs))], u_cls[k]))
        for k in range(len(vs)):
            roads.append(([_V(i, k) for i in range(len(us))], v_cls[k]))

    # ★★★ 2026-10-27（用户：「你的其他建筑太横平竖直了 一般城市不会这样」）：
    #   `organic` 原来只是**不等距 + 大方位角**，网格仍是正交的 ⇒ 画出来还是一张方方正正的图。
    #   真正的自然生长城镇，街道**方向本来就不一致**（一条街与邻街差几度，几代长出来的）。
    #   ⇒ 给网格**角点**加确定性抖动（±`SN_JITTER`），地块用它算：
    #     · 相邻两块**共享同一个角点**（抖的是点，不是块）⇒ 拼合仍然严丝合缝，不会裂；
    #     · 每条边的方向各不相同 ⇒ 建筑排出来方向也各不相同（`row_buildings` 沿边算）。
    #   ⚠ `grid` 抖动为 0：棋盘城是正交的，那是它的特征（唐长安、明清北京），不能抖。
    # [EN] ★★★ 2026-10-27 (the user: "your other buildings are too rectilinear; a town is not like
    # [EN] that"): `organic` used to be only uneven spacing + a large bearing, still an orthogonal grid,
    # [EN] so it came out square. A genuinely organic town has streets whose **directions disagree**
    # [EN] (one lane a few degrees off its neighbour, grown over generations). => Add a deterministic
    # [EN] jitter to the grid **vertices** (+-`SN_JITTER`), and build parcels from those: neighbouring
    # [EN] parcels **share the same vertex** (the points wobble, not the parcels), so they still tile
    # [EN] without gaps, while each edge's direction differs -- and `row_buildings` follows the edge, so
    # [EN] the building rows differ too. ⚠ `grid` jitters by 0: an orthogonal chessboard city is the
    # [EN] whole point of that form (Tang Chang'an, Ming-Qing Beijing) and must not wobble.

    lots: list = []
    lanes: list = []
    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            u0, u1 = us[i], us[i + 1]
            v0, v1 = vs[j], vs[j + 1]
            P00, P10 = _V(i, j), _V(i + 1, j)
            P11, P01 = _V(i + 1, j + 1), _V(i, j + 1)
            quad = [P00, P10, P11, P01]
            # 这个格子四邻四条街里最宽的那条，决定它该退回多少
            # [EN] The widest of the four bordering streets decides how far this cell retreats
            pad = max(_hw(u_cls[i]), _hw(u_cls[i + 1]),
                      _hw(v_cls[j]), _hw(v_cls[j + 1]))
            if net == NET_RADIAL:
                # ⚠ 极坐标里**两维单位不同**：半径是 px，角度是弧度。
                #   放射街的"半宽"在半径 r 处等于 `hw / r` 弧度 —— 用像素内缩去退角度那一维
                #   等于没退（实测 220 块压路）。两维各按自己的单位退。
                # [EN] ⚠ In polar coordinates the two axes have different units: radius in px, angle in
                # [EN] radians. A radial street's half-width at radius r is `hw / r` radians, so a
                # [EN] pixel inset does nothing on that axis (220 blocks measured). Inset each axis in
                # [EN] its own unit.
                _sag = 4.0        # 弦弓高的补偿（见 `nv` 那一段说明）
                a0 = u0 + _hw(u_cls[i]) + _sag
                a1 = u1 - _hw(u_cls[i + 1]) - _sag
                dth = (_hw(max(v_cls[j], v_cls[j + 1])) + _sag) / max(1.0, u0)
                v0p, v1p = v0 + dth, v1 - dth
                if (a1 - a0) < 14.0 or (v1p - v0p) <= 0.0:
                    continue
                lots.append([P(a0, v0p), P(a1, v0p), P(a1, v1p), P(a0, v1p)])
                continue
            # `organic`：零星地块**不建房**（空地/菜园/水塘）
            # [EN] `organic`: the odd parcel left **unbuilt** (open ground / garden / pond)
            if net == NET_ORGANIC and ((i * 7 + j * 11 + seed) % 17 == 0):
                continue
            inner = _inset_convex(quad, pad)
            if len(inner) < 3:
                continue
            # 巷：在**内缩后**的面上沿长边切一刀，两半各再退半个巷宽
            # [EN] Alley: cut the **inset** face along its long side, each half retreating by half an
            # [EN] alley width
            # ⚠ 退让量要按**巷这条路实际画多宽**算（`ROAD_SPEC[local]` 外宽 6），
            #   不能拿 `SN_LANE_W` 当路面宽度 —— 巷画出来是 6px 宽的双线，
            #   只退 2.7px 的话路面还是压在地块上（实测 44 块）。
            # [EN] ⚠ The retreat must use the **drawn** alley width (`ROAD_SPEC[local]` outer 6),
            # [EN] not `SN_LANE_W`: the alley renders as a 6px double line, and retreating only 2.7px
            # [EN] still leaves the surface on the parcel (44 measured).
            g = _hw(SC.RC_LOCAL)
            ex = max(_quad_edges(inner), key=lambda e: e[2])
            long_side = ex[2]
            if long_side >= SN_LANE_MIN:
                k = inner.index(ex[0])
                a0p, a1p = inner[k], inner[(k + 1) % len(inner)]
                b0p = inner[(k + 2) % len(inner)]
                b1p = inner[(k + 3) % len(inner)]
                m0 = ((a0p[0] + b1p[0]) / 2.0, (a0p[1] + b1p[1]) / 2.0)
                m1 = ((a1p[0] + b0p[0]) / 2.0, (a1p[1] + b0p[1]) / 2.0)
                dx, dy = m1[0] - m0[0], m1[1] - m0[1]
                ln = math.hypot(dx, dy) or 1.0
                nx, ny = dy / ln * g, -dx / ln * g
                # ⚠ 只推**巷那一侧的两个点**，另外两条边原地不动。
                #   第一版把整块平移 g ⇒ 外侧那条边也跟着移，压到了外面的大街
                #   （实测 44 块被巷"穿过"，其实是地块自己移出去撞上了街）。
                # [EN] ⚠ Move **only the two points on the alley side**; leave the other two edges
                # [EN] where they are. The first version translated the whole half by g, which pushed
                # [EN] its outer edge onto the street (measured: 44 blocks "crossed by an alley" were
                # [EN] really blocks that had moved out and hit a street).
                lots.append([a0p, a1p,
                             (m1[0] + nx, m1[1] + ny),
                             (m0[0] + nx, m0[1] + ny)])
                lots.append([(m0[0] - nx, m0[1] - ny),
                             (m1[0] - nx, m1[1] - ny),
                             b0p, b1p])
                lanes.append(([m0, m1], SC.RC_LOCAL))
            else:
                lots.append(inner)

    # ★ 先把路裁到图廓内（街网按外接圆铺，端点本来在图外）
    # [EN] First clip the roads to the neat line (the network is laid out on a circumscribed radius)
    clipped_roads: list = []
    for _pts, _cls in roads:
        for _k in range(len(_pts) - 1):
            _got = _clip_seg(_pts[_k], _pts[_k + 1], (x0, y0, x1, y1))
            if _got is not None:
                clipped_roads.append(([_got[0], _got[1]], _cls))
    roads = clipped_roads
    lanes = [(_pts, _cls) for (_pts, _cls) in lanes
             if all(x0 - 1 <= p[0] <= x1 + 1 and y0 - 1 <= p[1] <= y1 + 1 for p in _pts)]

    # ★★★ 2026-10-27（实测抓到的第二个真错）：街网是按**外接圆半径**铺的（旋转后四角也要盖住），
    #   于是边缘的地块会伸到绘图区外（实测图元 y 到 776，画布只有 600 —— 用户报过
    #   "地图出了对话框边界"）。⇒ 只留**四角都在绘图区内**的地块。
    #   ⚠ 不做多边形裁剪：边缘本来就被图廓裁切，缺一块是正常的；裁剪会引入一条
    #     多边形裁剪路径（又一处会漂的实现）。
    # [EN] ★★★ 2026-10-27 (second real bug measured): the network is laid out on a **circumscribed
    # [EN] radius** (so the corners are covered after rotation), which pushes edge parcels outside the
    # [EN] drawing area (measured: a primitive at y=776 on a 600-tall canvas -- the user had already
    # [EN] reported "the map goes outside the dialog"). => Keep only parcels whose **four corners are
    # [EN] inside the drawing area**. ⚠ No polygon clipping: the edge is cut by the neat line anyway and
    # [EN] a missing parcel is normal, while clipping would add another code path that can drift.
    # ⚠ 用**裁剪**而不是"丢掉四角在外的那块"：网格是按外接圆铺的，边缘一圈地块必然
    #   有一部分在图外，直接丢掉会让图廓里边空出一条（实测只剩 24 块，整圈没了）。
    #   真实地图的街区本来就被**图廓裁切**，所以裁成多边形是对的。
    # [EN] ⚠ **Clip** rather than "drop parcels whose corners are outside": the network is laid out on
    # [EN] a circumscribed radius, so the outer ring of parcels always partly falls outside and dropping
    # [EN] them empties a band inside the neat line (measured: only 24 left). Real maps cut their edge
    # [EN] blocks with the neat line, so clipping into a polygon is the correct treatment.
    kept: list = []
    for q in lots:
        got = _clip_rect(_orient(q), x0, y0, x1, y1) if _outside(q, x0, y0, x1, y1) else q
        if len(got) >= 3 and _poly_area(got) >= LOT_MIN_AREA:
            kept.append(got)
    # `spacing` 给判据读：棋盘城与自然城镇的**街距均匀度**是它们最硬的区别
    # （唐长安的里坊等距切出来；自然长出来的城镇一街一个距）。
    # [EN] `spacing` for the criteria: the **uniformity of street spacing** is the hardest distinction
    # [EN] between a chessboard town (Tang Chang'an's wards are cut at equal intervals) and one that
    # [EN] grew organically (one spacing per street).
    _ug = [abs(us[i + 1] - us[i]) for i in range(len(us) - 1)]
    _vg = [abs(vs[i + 1] - vs[i]) for i in range(len(vs) - 1) if net != NET_RADIAL]
    return {'roads': roads, 'lots': kept, 'lanes': lanes, 'bearing': th,
            'spacing': {'u': _ug, 'v': _vg}}


def _quad_edges(quad: list) -> list:
    """四边形的四条边 `[(p0, p1, 长度)]`。 English: the four edges with their lengths."""
    out = []
    for k in range(len(quad)):
        a = quad[k]
        b = quad[(k + 1) % len(quad)]
        out.append((a, b, math.hypot(b[0] - a[0], b[1] - a[1])))
    return out


def row_buildings(quad: list, *, avoid=(), seed: int = 0,
                  setback: float = LOT_SETBACK, depth_ratio: float = 0.52,
                  rows: int = 2) -> list:
    """在一块地块里**沿街**排建筑（朝向跟随地块的街边，不再轴对齐）。

    Args:
        quad: 地块（4 点）。
        avoid: 要让开的四边形/矩形（有名字的要地等）。
        seed: 抖动种子。
        setback: 建筑退街的距离（人行道）。
        depth_ratio: 进深占地块深度的比例。
        rows: 最多排几排（贴两条街各一排）。

    Returns:
        `[quad4, ...]` —— 每栋是一个**任意方向的四边形**（不是轴对齐矩形）。

    ## 为什么要按"边"排，不按"轴"排（2026-10-27 用户：「其他建筑太横平竖直了」）

    轴对齐是"坐标轴的方向"，不是"街道的方向"。真实城镇里建筑贴着街走：
    街一转，整排房子跟着转。地块本身带方位角（`streetnet` 的 `bearing`），
    于是"沿最长边排、法向取进深"这四行向量运算，自然给出**与街同向**的建筑群 ——
    不需要再额外判断"这排该转多少度"。

    ★ 而且这套算法对**斜的地块**同样成立（organic 的斜边、radial 的扇形），
      因为它只用向量，不假设任何坐标轴。
    ★ 两排是贴两条街各排一排（真实街区两侧都临街），中间留出的空隙就是后院/院墙。
    [EN] Lay buildings **along the street** inside one parcel, their orientation following the
    [EN] parcel's street edge. ## Why by edge, not by axis (the user, 2026-10-27: "your other
    [EN] buildings are too rectilinear"): axis-aligned is the *coordinate* axis, not the *street*
    [EN] direction. In a real town buildings follow the street: turn the street, the whole row turns.
    [EN] The parcel already carries the network's bearing (`streetnet`'s `bearing`), so "arrange along
    [EN] the longest edge, take the depth along the normal" -- four vector operations -- yields rows
    [EN] **parallel to the street** with no extra "how many degrees should this row turn" logic.
    [EN] ★ It also works for slanted parcels (organic edges, radial sectors) because it uses vectors
    [EN] only and assumes no coordinate axis. ★ Two rows sit against two streets (a real block fronts
    [EN] streets on both sides); the gap between them is the rear yard / party wall.
    """
    if len(quad) < 3:
        return []
    edges = _quad_edges(quad)
    k = max(range(len(edges)), key=lambda i: edges[i][2])
    p0, p1, _L = edges[k]
    L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    if L < LOT_MIN * 1.6:
        return []
    d = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
    nx, ny = -d[1], d[0]
    # 法向朝内：用四边形中心判定（地块可能是斜的，靠"上下左右"判不出来）
    # [EN] Point the normal inward using the parcel centre (a slanted parcel has no up/down)
    mx = sum(q[0] for q in quad) / len(quad)
    my = sum(q[1] for q in quad) / len(quad)
    midx, midy = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    if (mx - midx) * nx + (my - midy) * ny < 0:
        nx, ny = -nx, -ny
    # 地块沿法向的**可用深度**（取各点到 p0 的法向投影范围）
    proj = [(q[0] - p0[0]) * nx + (q[1] - p0[1]) * ny for q in quad]
    depth_avail = max(proj) - min(proj)
    if depth_avail < LOT_MIN * 1.4:
        return []

    out: list = []

    def _emit(base_a: tuple, base_b: tuple, nvec: tuple, depth: float, sd: int) -> None:
        """沿 base_a→base_b 排一排，进深朝 nvec。"""
        bx0, by0 = base_a
        ex, ey = base_b[0] - bx0, base_b[1] - by0
        LL = math.hypot(ex, ey)
        if LL < LOT_W * 0.8:
            return
        ux, uy = ex / LL, ey / LL
        for (t0, t1) in _vary(0.0, LL, LOT_W, seed=sd):
            w = (t1 - t0) - LOT_GAP
            if w < LOT_MIN:
                continue
            ax, ay = bx0 + ux * (t0 + LOT_GAP / 2.0), by0 + uy * (t0 + LOT_GAP / 2.0)
            # ★ 每栋进深**各自**差一点（同一排全一样深，看起来像梳子）。
            #   真实沿街院落本来就有深有浅（正房三进、厢房一进）。
            #   抖动是确定性的：只由这一栋的**位置**决定。
            # [EN] ★ Each building's depth varies a little: an identical row looks like a comb, while
            # [EN] real street frontages differ (a three-courtyard main hall vs a one-courtyard wing).
            # [EN] The wobble is deterministic, decided only by this building's position.
            dd = depth * (0.80 + 0.34 * (((int(t0) * 13 + sd * 7) % 11) / 10.0))
            dd = max(LOT_MIN, min(dd, depth * 1.14))
            q = [(ax, ay),
                 (ax + ux * w, ay + uy * w),
                 (ax + ux * w + nvec[0] * dd, ay + uy * w + nvec[1] * dd),
                 (ax + nvec[0] * dd, ay + nvec[1] * dd)]
            # ⚠ 必须用**射线法**：地块被图廓裁过可能是凹的，而"同侧判定"（凸）对凹多边形
            #   会把一部分**外部**点判成在内 —— 于是建筑排到街区外面（实测 102/151）。
            # [EN] ⚠ Must use **ray casting**: a parcel clipped by the neat line may be concave, and the
            # [EN] "same side" (convex) test accepts some **outside** points on a concave polygon, so
            # [EN] buildings ended up outside their block (102/151 measured).
            if not all(pt_in_poly(c, quad, tol=1.0) for c in q):
                continue
            if avoid and any(_quad_hits_any(q, b, pad=1.0) for b in avoid):
                continue
            out.append(q)

    depth = max(LOT_MIN, min(depth_avail * depth_ratio, depth_avail - setback - 1.0))
    _emit(p0, p1, (nx, ny), depth, seed + 1)
    if rows >= 2 and depth_avail >= 2.0 * (depth + setback + LOT_MIN * 0.6):
        # 第二排：贴对边（方向反过来，进深朝反法向）
        # [EN] Second row: against the opposite edge, depth along the opposite normal
        q0, q1 = edges[(k + 2) % len(edges)][0], edges[(k + 2) % len(edges)][1]
        _emit(q0, q1, (-nx, -ny), depth, seed + 2)
    return out



def _bilerp(quad: list, s: float, t: float) -> tuple:
    """四边形内的双线性插值：`(s,t) ∈ [0,1]²`。

    ★ 为什么用双线性而不是"矩形 + 旋转角"：地块可能是平行四边形、梯形甚至扇形
      近似四边形（`radial`），双线性对**任意凸四边形**都给出"在内部、四边随之"的点，
      不需要判断角度。位置用参数表示，尺寸按比例 ⇒ 缩放天然不会越界。
    ★ 顶点顺序必须是绕行顺序（`streetnet` 保证：p0→p1→p2→p3 一圈）。
    [EN] Bilinear interpolation inside a quad, `(s,t) in [0,1]^2`. ★ Why not "rectangle + rotation
    [EN] angle": parcels may be parallelograms, trapezoids or near-sector quads (radial), and bilinear
    [EN] works for **any convex quad** while keeping the four edges, with no angle logic. Positions are
    [EN] parametric and sizes are ratios, so scaling can never fall outside. ★ Vertices must be in
    [EN] winding order (which `streetnet` guarantees).
    """
    p00, p10, p11, p01 = quad[0], quad[1], quad[2], quad[3]
    ax = (1 - s) * p00[0] + s * p10[0]
    ay = (1 - s) * p00[1] + s * p10[1]
    bx = (1 - s) * p01[0] + s * p11[0]
    by = (1 - s) * p01[1] + s * p11[1]
    return ((1 - t) * ax + t * bx, (1 - t) * ay + t * by)


def sub_quad(quad: list, s0: float, s1: float, t0: float, t1: float) -> list:
    """四边形内的一个**同向子四边形**（参数区间）。

    ★ 2026-10-27：地块被图廓裁过之后可能是 3~6 个点（**不是四边形**）。
      双线性插值只对 4 点成立，直接传会崩在 `p00, p10, p11, p01 = quad`。
      这里对非 4 点退回**按其包围盒**取子矩形 —— 边缘地块本来就不该放要地
      （`place_anchors` 已优先选 4 点的地块），这条只是兜底，不让它崩。
    [EN] A **same-orientation sub-quad** (parameter range). ★ 2026-10-27: after the neat-line clip a
    [EN] parcel may have 3-6 vertices (**not** a quad). Bilinear interpolation needs exactly four and
    [EN] would crash on the unpack. For non-quads this falls back to a sub-rectangle of the bounding
    [EN] box -- an edge parcel should not carry a named building anyway (`place_anchors` prefers 4-vertex
    [EN] parcels); this is only a guard so it cannot crash.
    """
    if len(quad) != 4:
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        ax, ay = min(xs), min(ys)
        bx, by = max(xs), max(ys)
        return [(ax + (bx - ax) * s0, ay + (by - ay) * t0),
                (ax + (bx - ax) * s1, ay + (by - ay) * t0),
                (ax + (bx - ax) * s1, ay + (by - ay) * t1),
                (ax + (bx - ax) * s0, ay + (by - ay) * t1)]
    return [_bilerp(quad, s0, t0), _bilerp(quad, s1, t0),
            _bilerp(quad, s1, t1), _bilerp(quad, s0, t1)]


def place_anchors(groups: list, pos: dict, cells: list) -> list:
    """把每处**有名字的建筑群**安放进一个地块里（一个地块最多一处）。

    Args:
        groups: `compounds()` 的结果 `[(主体, 成员)]`。
        pos: `{名字: (x, y)}`。
        cells: 地块列表（`streetnet` 的 lots 内缩后）。

    Returns:
        `[(主体, 成员, quad)]`，`quad` 是要地在图上占的那块**同向四边形**。

    ## 为什么"安放进地块"，而不是"以自身坐标为中心画"

    2026-10-27 用户：「**主角所在建筑也只是城市街道中的普通一员**」。
    原来的写法是拿 `Place.xy` 当中心、按成员数放大一个地块 —— 那是"以它为中心"，
    于是它必然落在**路口/街区正中**这种显眼位置，看起来像规划图的焦点。
    真实城市里，有名字的那栋楼只是某一排沿街房子里的一个院子：它在地块里的位置
    由地块决定，不由自己的坐标决定。

    ★ 坐标仍然用了，但只用来**选哪块地块**（最近的），不再决定"画多大、画在哪"。
      这就是"普通一员"的具体含义：位置被城市吸收，不再自己发光。
    ★ 一个地块只放一处要地：两处挤一块会互相压，也会让那地块变成"超级街区"。
    [EN] Put each **named compound** into one parcel (at most one per parcel). Returns the quad it
    [EN] occupies. ## Why "put it into a parcel" instead of "centre it on its own coordinate" (the user,
    [EN] 2026-10-27: "the protagonist's building is just an ordinary member of the city streets"): the old
    [EN] code used `Place.xy` as the centre and inflated a parcel by member count, which is
    [EN] "centred on it" -- so it inevitably landed on a junction or mid-block as the focus of the
    [EN] plan. In a real town the named building is one yard in a row of street frontages: its place in
    [EN] the parcel comes from the parcel, not from its own coordinate. ★ The coordinate is still used,
    [EN] but only to **choose which parcel** (the nearest) -- never how big or where. That is what
    [EN] "an ordinary member" means concretely: the city absorbs it and it stops glowing. ★ One named
    [EN] compound per parcel: two in one would overlap and turn that parcel into a super-block.
    """
    out: list = []
    taken: set = set()
    for body, members in (groups or []):
        if not cells:
            break
        bx, by = pos[body.name]
        # ★★★ 2026-10-27（实测）：要地尺寸原来被**地块大小**吞掉了 —— 「特大」的大庙
        #   落在一块小地上，画出来比「小」的小庙还窄（33.2 vs 26.4），`size` 分档形同虚设。
        #   ⇒ 排序键里加一条：容不下它的地块**加重罚**（放最后），优先中心近且够大的。
        # [EN] ★★★ 2026-10-27 (measured): the named building's size was **swallowed by the parcel** --
        # [EN] a "huge" temple landed in a small parcel and came out narrower than a "small" shrine
        # [EN] (33.2 vs 26.4), making the size tiers meaningless. => The sort key now **penalises**
        # [EN] parcels too small for it, preferring a nearby parcel that can hold it.
        _sc = SIZE_SCALE_BLDG.get(str(getattr(body, 'size', '中')), 1.25)
        _want = BLDG_BASE * _sc

        def _fit(k: int) -> float:
            _q = cells[k]
            _sides = sorted(e[2] for e in _quad_edges(_q)) if len(_q) >= 3 else [0.0]
            _edge = _sides[-1]
            _short = _sides[0]
            _d2 = ((sum(q[0] for q in _q) / len(_q) - bx) ** 2
                   + (sum(q[1] for q in _q) / len(_q) - by) ** 2)
            # ★ 两个维度都要够：长边装得下 **且** 短边装得下。
            #   只看长边的话，一条 6px 深的窄地也能被选中 —— 要地画进去，中心离街不到 3px
            #   （实测 3 处地点"落在路面上"）。
            # [EN] ★ Both axes must fit: the long edge **and** the short one. Checking only the long
            # [EN] edge let a 6px-deep sliver be chosen, and the named building's centre ended up
            # [EN] within 3px of a street (measured: 3 places "on the carriageway").
            _ok_len = _edge >= _want * 1.15
            _ok_dep = _short >= max(10.0, _want * 0.38)
            return _d2 + (0.0 if (_ok_len and _ok_dep) else 90000.0)

        order = sorted(range(len(cells)), key=_fit)
        # 优先**四点**地块（要地要沿地块的边摆放；被图廓裁成 3~6 点的边缘地块只作退路）
        # [EN] Prefer **four-vertex** parcels (a named building follows the parcel's edges); parcels
        # [EN] clipped by the neat line into 3-6 vertices are only a fallback.
        pick = next((k for k in order if k not in taken and len(cells[k]) == 4), None)
        if pick is None:
            pick = next((k for k in order if k not in taken), None)
        if pick is None:
            continue
        taken.add(pick)
        quad = cells[pick]
        # 尺寸按 size 分档，但**上限是地块的 55%**（不因为"是主角"就更大地画）
        # [EN] Size follows `size` but is **capped at 55% of the parcel** (never inflated for "being
        # [EN] the protagonist")
        scale = SIZE_SCALE_BLDG.get(str(getattr(body, 'size', '中')), 1.25)
        want = BLDG_BASE * scale
        edge = max(e[2] for e in _quad_edges(quad)) or 1.0
        # ★ 2026-10-27：尺寸按**绝对像素**（`want`）换算成参数，下限只留一点点。
        #   第一版下限写 0.30/0.26，等于"至少占地块边长 30%" —— 于是地块越大、
        #   建筑绝对尺寸越大，"特大 vs 小"被地块大小盖过去了（实测大庙反而比小庙窄）。
        #   现在 w*edge ≈ want，地块只决定位置与朝向，不决定大小。
        # [EN] ★ 2026-10-27: the size is an **absolute pixel** value (`want`) converted to a parameter,
        # [EN] with only a small floor. The first version floored at 0.30/0.26, i.e. "at least 30% of
        # [EN] the parcel edge", so a bigger parcel meant a bigger building and the parcel size swallowed
        # [EN] the "huge vs small" difference (measured: the huge temple came out narrower). Now
        # [EN] w * edge ~= want: the parcel decides position and orientation only, never size.
        w = min(0.85, max(0.10, want / edge))
        d = min(0.66, max(0.12, want / max(1.0, edge * 0.75)))
        # 贴一条街：沿 s 方向居中、沿 t 方向靠边（t 大的一侧）
        s0 = 0.5 - w / 2.0
        s1 = 0.5 + w / 2.0
        t1 = 0.92
        t0 = max(0.06, t1 - d)
        out.append((body, members, sub_quad(quad, s0, s1, t0, t1)))
    return out


def _quad_hits_any(q: list, box4, *, pad: float = 1.0) -> bool:
    """四边形 `q` 与 `box4` 是否相交（用各自的**包围盒**判，足够；建筑本身很小）。

    ★ 用包围盒而不是多边形求交：这里的用途只是"让开"，容许 1~2px 的保守误差；
      真求交要引入一条多边形裁剪路径，反而多一处会漂的实现。
    [EN] Whether quad `q` intersects `box4`, judged by **bounding boxes** (enough; buildings are
    [EN] small). ★ Not exact polygon intersection: the purpose is "keep clear" and 1-2px of
    [EN] conservatism is fine, while exact intersection would add another code path that can drift.
    """
    def _bb(p):
        xs = [v[0] for v in p]
        ys = [v[1] for v in p]
        return (min(xs), min(ys), max(xs), max(ys))
    a = _bb(q)
    b = _bb(box4)
    return (min(a[2], b[2] + pad) - max(a[0], b[0] - pad) > 0.0
            and min(a[3], b[3] + pad) - max(a[1], b[1] - pad) > 0.0)




def _hits_any(r: tuple, boxes, *, pad: float = 1.0) -> bool:
    """矩形 `r` 是否与 `boxes` 里任一个**带 pad 相交**。

    [EN] Whether rectangle `r` intersects any of `boxes` (expanded by pad).
    """
    x0, y0, x1, y1 = r
    for b in boxes:
        ax0, ay0, ax1, ay1 = b
        if (min(x1, ax1 + pad) - max(x0, ax0 - pad) > 0.0
                and min(y1, ay1 + pad) - max(y0, ay0 - pad) > 0.0):
            return True
    return False


def block_buildings(poly: list, *, avoid=(), seed: int | None = None) -> list:
    """一个街区里**一排排无名建筑**的矩形（轴对齐、确定性）。

    Args:
        poly: 街区面（凸多边形，`city_blocks` 的输出）。
        avoid: 要**让开**的矩形 `(x0,y0,x1,y1)` —— 有名字的建筑群地块、独立地物的符号位置。
        seed: 抖动种子；不给就由街区位置算（同一块地永远同一份排布）。

    Returns:
        `[(x0, y0, x1, y1), ...]`，每个都是轴对齐矩形。

    ## 为什么要有这一层（2026-10-27 用户：「街道图里的其他建筑呢」）

    上一轮把街区画成了**极淡的地面**（那是修"道路穿越建筑"的必要一步：街区不是建筑），
    但修完之后地图上只剩"地块 + 两条命名的建筑群"，**街区里一栋房子都没有** ——
    真实城市地图上，地块之所以读得出来"这是一片城区"，正是因为里面填满了建筑。

    ## 为什么这不算编造

    ★ 街区面本身就是**推出来的**（Voronoi / 棋盘细分），它没有名字、没有归属；
      里面再画满"无名建筑体量"，是同一层推断的继续 —— 表达的是"这一片是建成区"，
      **不是**"这里有一栋叫某某楼的房子"。凡是有名字的建筑，一律走 `compounds()`（实心+有名），
      体量永远**没有说话的名字**，图例也如实写"无名体量"。
    ★ 制图上这是标准做法：GB/T 20257.1 在大比例尺下按**单幢**表示房屋、
      城市尺度按**建筑群**表示；USGS《Map Graphics and Generalisation》要求保留建筑的
      **大小差异与朝向**、省略小细节但保留基本形状。⇒ 所以这里：只画矩形、尺寸不一、
      沿街成排（朝向由街道决定），不做任何装饰。

    ## 排布规则（都在 u/v 局部坐标里算，横向街区与纵向街区共用一套）

    1. 街区 bbox 先**退 `LOT_SETBACK`** —— 留出人行道，建筑不贴着街；
    2. 长边方向切成若干**排**（`LOT_ROW` 进深），每排再切成若干**栋**（`LOT_W` 面宽）；
       切分用 `_vary`（确定性的不等分），于是没有两栋一样宽；
    3. 每栋的**进深**是所在排的 0.58~0.92 倍，且**单双排交替靠向两侧** ——
       真实的沿街建筑就是这样背靠背排的（中间留出后院/巷道），比"每排一样深"像得多；
    4. 四角必须都落在街区内（凸多边形的斜边会把角切掉，那一栋就不画）；
    5. 与 `avoid` 相交的不画（有名字的建筑群、桥/渡的符号位置都让出来）。

    ⚠ 单块街区少于 `LOT_MIN × 1.8` 见方就不排（那种小块其实是道路切出来的边角，
      填满反而像糊了一块砖）。
    [EN] The **rows of anonymous buildings** inside one block (axis-aligned, deterministic).
    ## Why this layer exists (the user, 2026-10-27: "where are the other buildings on the street
    [EN] map?"): last round made blocks the **light ground** (needed to fix "roads cut through
    [EN] buildings"), but then the map had only parcels plus two named compounds and **not one house
    [EN] inside any block** -- while on a real city map a parcel reads as "built-up area" precisely
    [EN] because it is filled with buildings. ## Why it is not fabrication: the block itself is
    [EN] **inferred** (Voronoi / grid subdivision), it has no name and no owner, and filling it with
    [EN] "anonymous massing" is the same level of inference -- it says "this is built-up ground", never
    [EN] "there is a building called X here". Anything with a name goes through `compounds()` (filled and
    [EN] labelled); massing is **never labelled**, and the legend says so. Cartographically this is
    [EN] standard: GB/T 20257.1 shows individual buildings at large scales and **building groups** at city
    [EN] scale; USGS's generalisation guide requires preserving **size differences and orientation**
    [EN] while dropping small detail. Hence: rectangles only, varied sizes, rows along the street.
    ## Layout (computed in local u/v so wide and tall blocks share one code path): (1) the block bbox
    [EN] is **inset by `LOT_SETBACK`** so buildings never touch the street; (2) the long axis is cut into
    [EN] **rows** (`LOT_ROW` deep), each row into **lots** (`LOT_W` frontage) with `_vary` (deterministic
    [EN] unequal split), so no two are the same width; (3) each building is 0.58-0.92 of its row depth
    [EN] and rows **alternate sides**, which is how real street frontages back onto each other (leaving
    [EN] rear yards and alleys); (4) all four corners must fall inside the block (a slanted edge simply
    [EN] drops that building); (5) anything intersecting `avoid` is skipped. ⚠ A block smaller than
    [EN] `LOT_MIN x 1.8` gets nothing (those are corner slivers cut by roads, and filling them looks like
    [EN] a brick dropped in).
    """
    if len(poly) < 3:
        return []
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    ix0, iy0 = min(xs) + LOT_SETBACK, min(ys) + LOT_SETBACK
    ix1, iy1 = max(xs) - LOT_SETBACK, max(ys) - LOT_SETBACK
    if (ix1 - ix0) < LOT_MIN * 1.8 or (iy1 - iy0) < LOT_MIN * 1.8:
        return []
    if seed is None:
        # 种子只来自**这块地的位置**：同一份数据永远同一份排布（本项目的"纯函数"纪律）
        # [EN] The seed comes only from **where this block is**: one dataset, one layout (pure function)
        seed = int(abs(round(ix0 * 7.0 + iy0 * 13.0))) % 97
    wide = (ix1 - ix0) >= (iy1 - iy0)
    u0, u1 = (ix0, ix1) if wide else (iy0, iy1)      # 沿街方向
    v0, v1 = (iy0, iy1) if wide else (ix0, ix1)      # 进深方向

    def box(uu0: float, vv0: float, uu1: float, vv1: float) -> tuple:
        return (uu0, vv0, uu1, vv1) if wide else (vv0, uu0, vv1, uu1)

    out: list = []
    for ri, (r0, r1) in enumerate(_vary(v0, v1, LOT_ROW, seed=seed + 3)):
        band = r1 - r0
        if band < LOT_MIN:
            continue
        depth = band * (0.58 + 0.34 * (((ri * 7 + seed) % 11) / 10.0))
        for (c0, c1) in _vary(u0, u1, LOT_W, seed=seed * 3 + ri):
            w = (c1 - c0) - LOT_GAP
            if w < LOT_MIN:
                continue
            uu0 = c0 + LOT_GAP / 2.0
            # 单双排交替：靠向两侧，中间自然留出后院/巷道
            # [EN] Rows alternate sides, leaving rear yards/alleys in between
            vv0 = (r0 + LOT_GAP / 2.0) if (ri % 2 == 0) else (r1 - LOT_GAP / 2.0 - depth)
            if vv0 < r0 or (vv0 + depth) > r1:
                vv0 = r0 + LOT_GAP / 2.0
            r = box(uu0, vv0, uu0 + w, vv0 + depth)
            corners = ((r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3]))
            if not all(_pt_in_convex(c, poly) for c in corners):
                continue
            if avoid and _hits_any(r, avoid, pad=1.0):
                continue
            out.append(r)
    return out


def _draw_massing(shapes: list, rects: list, pal: dict) -> None:
    """把无名建筑画成**一条 `fcv.Path` 里的许多子路径**（不是一栋两个图元）。

    ★ 为什么不逐栋画：一份城市图有几个街区、每街区十几栋 ⇒ 三四百栋。
      一栋两个图元（填充 + 描边）就是七八百个图元，画布会明显变慢。
      一条 Path 里塞全部子路径，**填充与描边各一条**，与栋数无关。
    ★ 颜色：比主体楼浅得多（`MASS_FILL`），比街区底纹深 —— 三层要能一眼分开：
      地面（最淡）→ 无名体量（中）→ 有名字的建筑（最深、带描边）。
    [EN] Draw the anonymous buildings as **many sub-paths inside one `fcv.Path`** (not two primitives
    [EN] per building). ★ Why: a city map has a few dozen blocks with a dozen buildings each, i.e. three
    [EN] or four hundred -- two primitives each means seven or eight hundred and the canvas visibly
    [EN] slows down. One Path holding every sub-path costs **one fill and one stroke**, regardless of the
    [EN] count. ★ Colour: much lighter than a main building (`MASS_FILL`), darker than the block tint, so
    [EN] the three layers (ground -> anonymous massing -> named building) separate at a glance.
    """
    if not rects:
        return
    els: list = []
    for q in rects:
        # ★ 2026-10-27：每栋现在是**任意方向的四边形**（沿街排，随街转向），
        #   不再是轴对齐矩形 —— 所以按点列画，不能解包成 (x0,y0,x1,y1)。
        # [EN] ★ 2026-10-27: each building is now an **arbitrary quad** (laid along the street and
        # [EN] turned with it), no longer an axis-aligned rectangle -- so draw by points, never unpack
        # [EN] into (x0, y0, x1, y1).
        els.append(fcv.Path.MoveTo(q[0][0], q[0][1]))
        els += [fcv.Path.LineTo(p[0], p[1]) for p in q[1:]]
        els.append(fcv.Path.Close())
    ink = pal.get('ink', '#4a4f57')
    paper = pal.get('paper', '#f8f4ea')
    shapes.append(fcv.Path(list(els), paint=ft.Paint(
        color=_mix(paper, ink, MASS_FILL), style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Path(list(els), paint=ft.Paint(
        color=_mix(paper, ink, MASS_FILL + 0.20), stroke_width=0.55,
        style=ft.PaintingStyle.STROKE)))




def _drop_slivers(polys: list, *, rel: float = 0.18, floor: float = 120.0) -> list:
    """丢掉**碎屑小块**（被路切出来的小三角、小尖角）。

    ★★★ 2026-10-27（用户：「建筑有一些三角和异形建筑 因为在现实中不太常见」）：
      除了 Voronoi 的异形，还有一个来源 —— 道路把街区块切开时，会在斜角处
      剩下**三角形碎屑**（实测 1 块，297px²，而中位数是 2765px²）。
      地图上那种"半个三角"既不像地块也不像建筑，就是用户说的"异形"。

    ★ 这不是新发明，就是制图学的**综合取舍**：GB/T 20257.1 规定
      "房屋面积小于 2mm² 的可综合取舍"、"轮廓凸凹小于 0.4mm 时可综合取舍"。
      换算到这张图上：小于中位数 18% 的碎屑不画。

    ★ 为什么用**相对**阈值（中位数的比例）而不是固定的平方像素：
      不同数据密度下街区尺寸差很多；固定阈值在密图上会全丢、在疏图上丢不掉。
      同时给一个绝对下限（`floor`），防止"整张图只有 3 块时中位数很小"把正常块误丢。

    ★ 丢了不留洞：这些碎屑本来就夹在路与街区之间，路面那层带会盖住它，
      视觉上没有缺口。
    [EN] Drop **sliver fragments** (the small triangles and slivers left where a road cuts a block).
    ★★★ 2026-10-27 (the user: "some buildings are triangles or odd shapes, uncommon in reality"):
    [EN] besides the Voronoi irregularity there was a second source -- cutting blocks along roads leaves
    [EN] **triangular slivers** at oblique corners (measured: one, 297px^2, against a median of
    [EN] 2765px^2). Such a "half triangle" is neither a parcel nor a building, and it is exactly the
    [EN] "odd shape" the user meant. ★ This is not invented: it is cartographic **generalisation**
    [EN] (GB/T 20257.1: footprints under 2mm^2 and indentations under 0.4mm may be generalised away).
    [EN] ★ Why a **relative** threshold (a fraction of the median) rather than fixed pixels: block sizes
    [EN] vary with data density, and a fixed number would delete everything on a dense map and nothing on
    [EN] a sparse one. An absolute floor prevents a tiny median from deleting normal blocks. ★ Dropping
    [EN] leaves no hole: these slivers sit between a road and a block, and the road surface covers them.
    """
    ps = [p for p in (polys or []) if len(p) >= 3]
    if not ps:
        return []

    def _area(p) -> float:
        s = 0.0
        for i in range(len(p)):
            a, b = p[i], p[(i + 1) % len(p)]
            s += a[0] * b[1] - b[0] * a[1]
        return abs(s) / 2.0

    areas = sorted(_area(p) for p in ps)
    med = areas[len(areas) // 2]
    cut = max(floor, med * rel)
    keep = [p for p in ps if _area(p) >= cut]
    return keep or ps          # 全被丢掉时退回原样（宁可有个碎屑，也不能整张图空）


def _clip_rect(poly: list[tuple[float, float]], x0: float, y0: float,
               x1: float, y1: float) -> list[tuple[float, float]]:
    """把凸多边形裁到矩形内（四条半平面各裁一次，全用 `_clip_half`）。

    ★ 复用 `_clip_half` 而不另写裁剪：一条"保留 x>=x0"的半平面，就是
      `s=(x0+1,0)`、`o=(x0-1,0)` 这一对点的垂直平分线。不写第二套裁剪
      （本项目"同一件事两处实现必然漂"）。
    [EN] Clip a convex polygon to a rectangle (four half-plane cuts, all via `_clip_half`). ★ Reuse
    [EN] rather than a second clipper: "keep x>=x0" is exactly the bisector of `(x0+1,0)` and
    [EN] `(x0-1,0)`. Do not write a second clipper (this project's "two implementations always drift").
    """
    out = list(poly)
    for (sx, sy, ox, oy) in ((x0 + 1, 0.0, x0 - 1, 0.0),
                             (x1 - 1, 0.0, x1 + 1, 0.0),
                             (0.0, y0 + 1, 0.0, y0 - 1),
                             (0.0, y1 - 1, 0.0, y1 + 1)):
        out = _clip_half(out, float(sx), float(sy), float(ox), float(oy))
        if len(out) < 3:
            return []
    return out


def city_mode(places, links=None) -> str:
    """这张城市图该画**街区**还是画**导览**。

    ★ 判据只有一条：**地点够不够密**（`CITY_BLOCKS_MIN`）。
      · 不够 ⇒ 这些是几处地物，画街区就是把它们硬切成地块（用户看到的"一摞长方形"）；
      · 够 ⇒ 有"一片城区"的感觉，街区才成立。
    ★ 为什么**不**用"路能不能围出闭合面"当判据：我们的 `links` 是"这两处之间有路"的
      关系，不是路网拓扑 —— 拿它判闭合会得出"几乎永远不闭合"，那就等于永远不画街区。
      用地点数更诚实：它说的是"这够不够密到能叫一片城区"。
    ★ 也不看风格（`路网=grid` 之类）：那是"街区**怎么**切"，不是"要不要有街区"。
    [EN] Should this city map draw **blocks** or a **guide**? ★ One rule: **are there enough places**
    [EN] (`CITY_BLOCKS_MIN`). Fewer => these are a handful of features, and drawing blocks carves them
    [EN] into parcels (the "stack of rectangles" the user saw); enough => it reads as a stretch of town,
    [EN] and blocks make sense. ★ Why **not** "can the roads enclose an area": our `links` are "there
    [EN] is a road between these two" relations, not network topology -- judging closure from them would
    [EN] say "almost never closed", i.e. never draw blocks. Counting places is more honest: it answers
    [EN] "is this dense enough to call a stretch of town". ★ Nor does the profile decide (grid/organic
    [EN] says **how** to cut blocks, not **whether** to have them).
    """
    n = len([p for p in (places or []) if p is not None])
    return CITY_BLOCKS if n >= CITY_BLOCKS_MIN else CITY_AREA


#: 地物类型 → 图例里怎么说（导览图的图例要解释"这个三角是什么"）。
#: 键是 `map_layout.SHAPES` 的闭集；没列到的补一句通用的。
# [EN] Feature kind -> legend wording (a guide map's legend must explain "what is that triangle").
# [EN] Keys are the closed set `map_layout.SHAPES`; anything unlisted gets a generic line.
GLYPH_LABEL = {
    '屋': '房屋 / 屋舍', '院': '院落（露天）', '亭': '亭 / 榭',
    '门': '门 / 牌坊', '桥': '桥', '渡': '渡口 / 码头',
    '树': '林地', '山': '山丘', '塔': '塔 / 楼阁',
    '台': '台 / 台地', '市': '市集 / 街市',
}

#: 路网形态（**闭集**）。与 `worldstyle.Style.路网` 一一对应。
#:
#: ★★★ 2026-10-26：这三个值**一直写在档案里、从来没被读过**（`grep '\.路网'` 零命中）。
#:   于是中式都城（坊市棋盘）、西式联排镇（自然生长）、环形空间站（放射）
#:   画出来是同一张 Voronoi 图 —— 用户看到的是"换了个世界，地图长得一模一样"。
#:   字段写了不等于生效，这一条是本项目栽过最多次的坑。
# [EN] Street-network forms (**a closed set**), in one-to-one correspondence with
# [EN] `worldstyle.Style.路网`. ★★★ 2026-10-26: these three values were **written into every profile
# [EN] and never read** (zero hits for `.路网`), so a Chinese grid capital, a Western organic town
# [EN] and a radial ring station all came out as the same Voronoi diagram -- the user's complaint
# [EN] would be "new world, same map". A field that is written but not read is this project's most
# [EN] frequent pit.
NET_ORGANIC = 'organic'
NET_GRID = 'grid'
NET_RADIAL = 'radial'
NETS = (NET_ORGANIC, NET_GRID, NET_RADIAL)

#: 图例里怎么说街区（读者要能对上"为什么这块是方的、那块是斜的"）
# [EN] How the legend words the blocks, so the reader can connect "why square here, slanted there"
NET_LABEL = {
    NET_ORGANIC: '街区（自然生长，就近分片）',
    NET_GRID: '街区（棋盘，横直街划分）',
    NET_RADIAL: '街区（环形放射）',
}

#: 城际形态（**闭集**）：地形为主 / 政区为主 / 航路（海图）。
#: `nautical` 是 2026-10-26 加的 —— 舟船的世界没有政区，把航路画成官道就是编国界。
# [EN] Region-map forms (**a closed set**): terrain-led, administrative-led, or nautical chart.
# [EN] `nautical` was added 2026-10-26: a ship's world has no administrative divisions, and drawing
# [EN] sea routes as highways invents borders.
REGION_TERRAIN = 'terrain'
REGION_ADMIN = 'administrative'
REGION_NAUTICAL = 'nautical'
REGION_FORMS = (REGION_TERRAIN, REGION_ADMIN, REGION_NAUTICAL)


def net_of(style) -> str:
    """这个档案的城市路网形态；认不出给 `organic`（自然生长，最不冒犯）。

    [EN] The city street-network form for this profile; `organic` when unknown (least opinionated).
    """
    v = str(getattr(style, '路网', '') or '')
    return v if v in NETS else NET_ORGANIC


def region_form(style) -> str:
    """这个档案的城际形态；认不出给 `terrain`。

    [EN] The region-map form for this profile; `terrain` when unknown.
    """
    v = str(getattr(style, '城际', '') or '')
    return v if v in REGION_FORMS else REGION_TERRAIN


def _uniq_near(vals, tol: float) -> list[float]:
    """排序后合并"相距小于 tol"的值（把两次落点合并成一条街）。纯确定性。

    [EN] Sort and merge values closer than tol (two near-identical drops become one street).
    """
    out: list[float] = []
    for v in sorted(float(x) for x in vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _bounds(vals: list[float], lo: float, hi: float) -> list[float]:
    """一维 Voronoi 的**边界**：相邻两值的**中点**（＝垂直平分线在这一维上的投影）。

    ★ 用中点而不是用那条街本身：街区是"两块地面"，边界在两个落点**之间**。
      这与 `voronoi()`（二维垂直平分线）是同一个语义，所以 grid 与 organic 不会打架：
      grid 只是"把二维 Voronoi 拆成一维乘积"，切出来的格子必然是矩形。
    [EN] The 1-D Voronoi **boundaries**: midpoints between neighbours (the projection of the
    [EN] perpendicular bisector). ★ Midpoints rather than the streets themselves, because a block is a
    [EN] piece of ground between two drops -- the same semantics as `voronoi()`, so grid is literally
    [EN] the product of two 1-D Voronoi divisions and its cells are necessarily rectangles.
    """
    b = [float(lo)]
    for a, c in zip(vals, vals[1:]):
        b.append((float(a) + float(c)) / 2.0)
    b.append(float(hi))
    return b


def grid_cells(pos: dict, box: tuple) -> list[list[tuple[float, float]]]:
    """**棋盘街区**：横向按 x 的一维 Voronoi、纵向按 y 的一维 Voronoi，乘起来就是矩形块。

    ★ 为什么这样是"真的棋盘"而不是"画一层网格线"：网格线的位置来自**地点自己的坐标**
      （横直街就落在两处地点的中间），所以街区与地点一一对得上；凭空画一层等距网格
      才是"编出来的路"。
    [EN] **Grid blocks**: the product of a 1-D Voronoi on x and one on y, hence rectangles. ★ Why
    [EN] this is a real grid rather than "a decorative mesh": the street positions come from the
    [EN] places' own coordinates, so blocks correspond to places; an evenly spaced mesh would be
    [EN] invented roads.
    """
    x0, y0, x1, y1 = (float(v) for v in box)
    if not pos:
        return []
    xs = _uniq_near([p[0] for p in pos.values()], (x1 - x0) * 0.10)
    ys = _uniq_near([p[1] for p in pos.values()], (y1 - y0) * 0.10)
    xb = _bounds(xs, x0, x1)
    yb = _bounds(ys, y0, y1)
    cells: list[list[tuple[float, float]]] = []
    for i in range(len(xb) - 1):
        for j in range(len(yb) - 1):
            if xb[i + 1] - xb[i] < 6.0 or yb[j + 1] - yb[j] < 6.0:
                continue
            cells.append([(xb[i], yb[j]), (xb[i + 1], yb[j]),
                          (xb[i + 1], yb[j + 1]), (xb[i], yb[j + 1])])
    return cells


def radial_cells(pos: dict, box: tuple) -> list[list[tuple[float, float]]]:
    """**环形放射街区**：极坐标下的 Voronoi（按方位分扇、按半径分环）。

    ★ 极点取所有地点坐标的**重心**（确定性），不是"看起来像中心"的那个 ——
      取某个地点当极点会让整张图随一处改名而翻面。
    ★ 为什么这算"不编"：扇界落在相邻两处地点的**方位中点**、环界落在**半径中点**，
      与二维 Voronoi 的垂直平分线是同一个"就近归属"语义，只是换了坐标系。
    [EN] **Radial blocks**: a Voronoi in polar coordinates (sectors by bearing, rings by radius).
    ★ The pole is the **centroid** of the places (deterministic); picking "the one that looks
    [EN] central" would flip the whole map when one place is renamed. ★ Why this is not fabrication:
    [EN] sector edges fall at the **mid-bearing** between neighbouring places and ring edges at the
    [EN] **mid-radius**, the same "nearest wins" semantics as the 2-D bisectors, in another frame.
    """
    x0, y0, x1, y1 = (float(v) for v in box)
    if not pos:
        return []
    cx = sum(p[0] for p in pos.values()) / len(pos)
    cy = sum(p[1] for p in pos.values()) / len(pos)
    polar = []
    for p in pos.values():
        dx, dy = float(p[0]) - cx, float(p[1]) - cy
        polar.append((math.atan2(dy, dx), math.hypot(dx, dy)))
    if len(polar) < 2:
        return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]
    angs = sorted(a for a, _r in polar)
    radii = sorted(r for _a, r in polar)
    # 扇界：相邻方位的中点（首尾环绕）
    edges = [(angs[i] + angs[(i + 1) % len(angs)]) / 2.0 for i in range(len(angs))]
    # 首尾那一份要跨 ±π：把它挪到 -π 那边算
    edges[-1] = ((angs[-1] + angs[0] + 2 * math.pi) / 2.0) - math.pi * 2
    edges.sort()
    # 环界：相邻半径的中点，外加"比最小半径再小一圈"和"比最大半径再大一圈"
    rmax = max(radii) * 1.35 + 20.0
    redges = [0.0]
    for a, b in zip(radii, radii[1:]):
        redges.append((a + b) / 2.0)
    redges.append(rmax)
    redges = _uniq_near(redges, 8.0)
    cells: list[list[tuple[float, float]]] = []
    for i in range(len(edges)):
        a0 = edges[i]
        a1 = edges[(i + 1) % len(edges)]
        if a1 <= a0:
            a1 += 2 * math.pi
        for j in range(len(redges) - 1):
            r0, r1 = redges[j], redges[j + 1]
            if r1 - r0 < 6.0:
                continue
            poly: list[tuple[float, float]] = []
            steps = 7
            for k in range(steps + 1):
                t = a0 + (a1 - a0) * k / steps
                poly.append((cx + r1 * math.cos(t), cy + r1 * math.sin(t)))
            for k in range(steps, -1, -1):
                t = a0 + (a1 - a0) * k / steps
                poly.append((cx + r0 * math.cos(t), cy + r0 * math.sin(t)))
            # 裁进绘图区：只留"有点落在框内"的格子（框外的看不见，也没必要画）
            if not any(x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1 for x, y in poly):
                continue
            cells.append(poly)
    return cells



# ══════════════════════════════════════════════════════════════════════
#  城市图：街区 + 分级路网 + 水系 + POI
# [EN] City map: blocks + graded road network + water + POIs
# ══════════════════════════════════════════════════════════════════════
def _road_seg(shapes: list, a: tuple, b: tuple, cls: str, pal: dict, *,
              k: float = 1.0, dashed: bool = False, layer: str = 'all') -> None:
    """画**一段**路（双线带；`trunk` 另加中心线）。城市图／城际图／甲板图共用这一份。

    ★ 为什么抽出来：原来城市图与城际图各写一遍"外宽 wall + 内宽 paper + 中心线"，
      两份参数必然漂（本项目头号老坑）。这里只有一个实现，宽度来自 `scale.ROAD_SPEC`。
    ★ `dashed=True` 用于**航路**：海图上航线是虚线（实线会被读成陆上的官道/堤）。
    ★ `layer='casing'|'core'|'all'`：**分遍**画（城市图用）——
      先把这一档所有路的**外框**画一遍、再把**内芯**画一遍，路口处路面自然并成一块，
      双线在路口断开（标准地图的画法）。默认 `'all'` = 一次画完（城际图／甲板图用）。
    [EN] Draw **one segment** of road (double band; `trunk` also gets a centre line), shared by the
    [EN] city / region / deck maps. ★ Extracted because the city and region maps each had their own
    [EN] copy of "outer wall stroke + inner paper stroke + centre line", and two parameter sets
    [EN] always drift (this project's number-one pit). ★ `dashed=True` is for **sea routes**: on a
    [EN] chart a route is dashed (a solid line reads as a highway or a dyke on land). ★
    [EN] `layer='casing'|'core'|'all'` draws in **passes** (used by the city map): all casings of a
    [EN] class, then all cores of that class, so the surfaces merge at a junction and the double
    [EN] lines break there (standard cartography). Default `'all'` draws it in one go.
    """
    outer, inner, centre = SC.ROAD_SPEC.get(cls, SC.ROAD_SPEC[SC.RC_LOCAL])
    outer *= k
    inner *= k
    if dashed:
        _dashed(shapes, a, b, pal.get('wall', '#b9b1a0'), dash=7.0, gap=4.5, width=max(1.2, outer))
        return
    if layer in ('all', 'casing'):
        shapes.append(fcv.Line(a[0], a[1], b[0], b[1],
                              paint=ft.Paint(color=pal.get('wall', '#b9b1a0'),
                                             stroke_width=outer,
                                             stroke_cap=ft.StrokeCap.ROUND,
                                             style=ft.PaintingStyle.STROKE)))
    if layer in ('all', 'core'):
        shapes.append(fcv.Line(a[0], a[1], b[0], b[1],
                              paint=ft.Paint(color=pal.get('paper', '#f8f4ea'),
                                             stroke_width=inner,
                                             stroke_cap=ft.StrokeCap.ROUND,
                                             style=ft.PaintingStyle.STROKE)))
        if centre:
            shapes.append(fcv.Line(a[0], a[1], b[0], b[1],
                                  paint=ft.Paint(color=_mix(pal.get('paper', '#f8f4ea'),
                                                            pal.get('ink', '#4a4f57'), 0.42),
                                                 stroke_width=1.1,
                                                 stroke_cap=ft.StrokeCap.ROUND,
                                                 style=ft.PaintingStyle.STROKE)))


def compound_box(body, members: list, pos: dict) -> dict:
    """一处建筑群的**地块与主体尺寸**（`_draw_compound` 与"体量让位"共用这一份）。

    Returns:
        `{'bx','by','w','h','x0','y0','x1','y1','bw','bh'}`。

    ★ 为什么必须抽出来：城市图里的**无名体量**要知道"哪里有名字的建筑、要让开"，
      而它让开的范围必须与 `_draw_compound` 真正画出来的地块**一模一样**。
      两处各算一遍必然漂（本项目的老坑），表现是"体量压进了建筑群的地块里"。
    ★ 地块**以主体为中心、按成员数放大**，不追随成员坐标：`Place.xy` 是"位置"不是
      "尺寸"，实测那份数据里院子离楼 240px，追随坐标会把地块撑成 172×192 的巨无霸。
    [EN] The **parcel and main-building size** of one compound, shared by `_draw_compound` and by the
    [EN] massing's "keep clear" test. ★ Why extracted: the anonymous massing must avoid exactly the
    [EN] parcel that `_draw_compound` actually draws; computing it twice always drifts (this project's
    [EN] classic bug) and shows up as "massing pushed into the named compound's parcel". ★ The parcel is
    [EN] **centred on the main building and scaled by member count**, never following member
    [EN] coordinates: `Place.xy` is a *position*, not a *size*, and in the measured data the yard sat
    [EN] 240px away, which ballooned the parcel to 172x192.
    """
    bx, by = pos[body.name]
    scale = SIZE_SCALE_BLDG.get(str(getattr(body, 'size', '中')), 1.25)
    w = BLDG_BASE * scale * (1.0 + 0.42 * len(members))
    h = BLDG_BASE * scale * (1.0 + 0.30 * len(members))
    return {
        'bx': bx, 'by': by, 'w': w, 'h': h,
        'x0': bx - w / 2.0, 'y0': by - h / 2.0, 'x1': bx + w / 2.0, 'y1': by + h / 2.0,
        'bw': min(w * 0.62, BLDG_BASE * scale),
        'bh': min(h * 0.58, BLDG_BASE * scale * 0.78),
    }


def _draw_compound(shapes: list, body, members: list, pos: dict, pal: dict,
                   font: str | None, *, here: bool = False,
                   quad: list | None = None) -> dict:
    """画**一处建筑群**：主体楼（实心矩形）+ 院子（空心矩形）+ 一处整体轮廓。

    Returns:
        `{'box': (x0,y0,x1,y1), 'label_at': (x,y), 'kind': str}`

    ## 为什么这样画（2026-10-27 用户三句话逐条对应）

    * 「院子 临河楼 后院井台 这几个都是属于临河楼的部分」 ⇒ 一组合成**一处**，
      不再各画一处建筑；
    * 「建筑有一些三角和异形建筑 因为在现实中不太常见」 ⇒ 轮廓**只由轴对齐矩形拼**，
      院子与主体按相对位置拼成 L 形或"楼＋院"两段（GB/T 20257.1：小比例尺只用正方形和矩形）；
    * 「所有建筑大小都一样也不太合理」 ⇒ 尺寸按 `Place.size` 分档（`SIZE_SCALE_BLDG`），
      并且**主体比院子大**、成员多的群整体更大（USGS：preserve the size differences）。

    ## 画法（层序 = 从下往上）
    1. 整个群的**地块轮廓**（细线、浅底）—— 表示"这一片是它的院子范围"；
    2. 院子（见天）画**空心**矩形：只有描边 + 极浅底。空心=露天，这是制图惯例；
    3. 主体楼画**实心**矩形（`pal['ink']` 系），并按楼名后缀加一个小记号（寺/塔带尖顶）。
    ⚠ 不画屋顶晕线、不画门——这个尺度上它们只会糊成一片（GB/T 20257.1 的"综合取舍"）。
    [EN] Draw **one compound**: the main building (filled rectangle) + its yards (hollow rectangles) +
    [EN] one overall parcel outline. ## Why (each of the user's three points, 2026-10-27): "the
    [EN] courtyard, the building and the well terrace all belong to that building" => one compound, not
    [EN] three structures; "some buildings are triangles or odd shapes, uncommon in reality" => outlines
    [EN] are built **only from axis-aligned rectangles**, the yard and the building forming an L or a
    [EN] two-part "building + yard" (GB/T 20257.1: small scales use only squares and rectangles); "it is
    [EN] unreasonable that every building is the same size" => sizes follow `Place.size`
    [EN] (`SIZE_SCALE_BLDG`), the building is larger than its yard, and a compound with more members is
    [EN] larger overall (USGS: preserve the size differences). ## Layer order (bottom up): the parcel
    [EN] outline (thin, light), the yards as **hollow** rectangles (hollow = open sky, the cartographic
    [EN] convention), the main building as a **filled** rectangle with a small mark for its kind.
    [EN] ⚠ No roof hatching, no doors -- at this scale they only smear (GB/T 20257.1's "generalisation").
    """
    if quad:
        # ★★★ 2026-10-27：要地**落在它所属的地块里**（`place_anchors` 给的四边形），
        #   于是它的朝向 = 那排沿街房子的朝向，尺寸不超过地块的 55%。
        #   "主角所在建筑也只是城市街道中的普通一员"——它的位置由城市决定，不由自己发光。
        # [EN] ★★★ 2026-10-27: the named building **sits in its parcel** (the quad from
        # [EN] `place_anchors`), so its orientation is that row's orientation and its size is capped at
        # [EN] 55% of the parcel. "The protagonist's building is just an ordinary member of the city
        # [EN] streets" -- the city decides where it is; it does not glow.
        return _draw_anchor(shapes, body, members, pos, pal, font, quad, here=here)
    g = compound_box(body, members, pos)
    bx, by, w, h = g['bx'], g['by'], g['w'], g['h']
    x0, y0, x1, y1 = g['x0'], g['y0'], g['x1'], g['y1']

    # ★★★ 2026-10-27（重绘时量出来的第二个错）：**地块必须紧凑，以主体为中心**。
    #
    #   第一版我把地块**外扩到包住所有成员**（`x0 = min(x0, 成员x - w/2)`）。
    #   实测那份数据里院子在 (590,219)、楼在 (365,359)，相距 240px ⇒ 地块被撑成
    #   **172×192px** 的一块巨无霸，图上像是"一个占了半条街的大院"，
    #   而且把内容整体拉偏（判据 O3 报中心偏 +128,+162）。
    #
    #   为什么追随成员坐标是错的：`Place` 的 xy 是**城市图上的位置**，
    #   而"楼和它的院子"在城市尺度上本来是**一处紧凑的院落**（院子就贴着楼）。
    #   坐标把它们放远了，是坐标的粗糙，不是"院子真的隔着 240px"。
    #   制图上正确的处理是 GB/T 20257.1 的"建筑群按外围真实位置表示、内部简化"：
    #   外围 = 主体位置，内部 = 相对布局。
    #
    #   ⇒ 地块以主体中心为准；院子按它**相对主体的方位**（上/下/左/右）排在内部。
    #     方位信息保留（"后院在北边"仍然读得出来），尺寸不失控。
    # [EN] ★★★ 2026-10-27 (the second bug measured while re-drawing): **the parcel must be compact and
    # [EN] centred on the main building.** The first version expanded the parcel to **enclose every
    # [EN] member** (`x0 = min(x0, member.x - w/2)`). Measured, the yard sits at (590, 219) and the
    # [EN] building at (365, 359) -- 240px apart -- so the parcel ballooned to **172x192px**, reading as
    # [EN] "one compound taking half the street" and dragging the whole layout off-centre (criterion O3
    # [EN] reported +128,+162). Why following member coordinates is wrong: `Place.xy` is a **position on
    # [EN] the city map**, while "a building and its yard" is in reality **one compact compound** (the
    # [EN] yard abuts the building). Coordinates placing them far apart reflect coarse coordinates, not
    # [EN] "the yard is genuinely 240px away". The cartographic treatment is GB/T 20257.1's "building
    # [EN] groups are shown by the true position of their outline, the interior simplified": outline =
    # [EN] the main building's position, interior = relative layout. => The parcel is centred on the main
    # [EN] building; each yard is placed inside by its **bearing from the main building**, so the bearing
    # [EN] is preserved ("the rear yard is to the north") while the size stays sane.
    yards = [m for m in members if _is_open(m)]
    bw, bh = g['bw'], g['bh']

    edge = pal.get('ink', '#4a4f57')
    paper = pal.get('paper', '#f8f4ea')
    col = pal.get('here', '#b23028') if here else edge

    # ① 地块轮廓：这一处院落的范围（细线，不填）
    shapes.append(fcv.Rect(x0, y0, x1 - x0, y1 - y0, border_radius=1.0,
                           paint=ft.Paint(color=_mix(paper, edge, 0.34),
                                          stroke_width=1.1,
                                          style=ft.PaintingStyle.STROKE)))

    # ② 院子：**空心**矩形（露天），按方位排在主体四周
    # [EN] Yards: **hollow** rectangles (open sky), placed around the building by bearing
    for m in yards:
        mx, my = pos[m.name]
        dxm, dym = mx - bx, my - by
        # 归一化成四档方位（东南西北），不用连续角度 —— 小块上斜着摆会碰到建筑
        if abs(dxm) >= abs(dym):
            horiz = dxm >= 0
            yx0 = (x1 - w * 0.36) if horiz else x0
            yy0 = by - h * 0.28
            yw, yh = w * 0.36, h * 0.56
        else:
            yx0 = bx - w * 0.28
            yy0 = (by - h * 0.30) if dym < 0 else (by + h * 0.02)
            yw, yh = w * 0.56, h * 0.28
        shapes.append(fcv.Rect(yx0, yy0, yw, yh,
                               paint=ft.Paint(color=_mix(paper, pal.get('wall', '#b9b1a0'), 0.06),
                                              style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Rect(yx0, yy0, yw, yh,
                               paint=ft.Paint(color=_mix(paper, edge, 0.42),
                                              stroke_width=1.0,
                                              style=ft.PaintingStyle.STROKE)))

    # ③ 主体楼：**实心**矩形（按 size 定大小，但不超过地块）
    bxc, byc = bx, by
    shapes.append(fcv.Rect(bxc - bw / 2.0, byc - bh / 2.0, bw, bh, border_radius=1.0,
                           paint=ft.Paint(color=_mix(paper, col, 0.72),
                                          style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Rect(bxc - bw / 2.0, byc - bh / 2.0, bw, bh, border_radius=1.0,
                           paint=ft.Paint(color=col, stroke_width=1.0,
                                          style=ft.PaintingStyle.STROKE)))
    # ④ 类型记号：寺/塔/观 加一个尖顶（**只加一个记号，不改轮廓**——异形要避免）
    kind = str(getattr(body, 'shape', '屋') or '屋')
    nm = str(getattr(body, 'name', '') or '')
    if any(k in nm for k in ('寺', '塔', '观', '庙', '阁')) or kind == '塔':
        shapes.append(fcv.Path(
            [fcv.Path.MoveTo(bxc - 4.0, byc - bh / 2.0 - 1.0),
             fcv.Path.LineTo(bxc, byc - bh / 2.0 - 7.0),
             fcv.Path.LineTo(bxc + 4.0, byc - bh / 2.0 - 1.0)],
            paint=ft.Paint(color=col, stroke_width=1.3,
                           style=ft.PaintingStyle.STROKE)))
    return {'box': (x0, y0, x1, y1), 'label_at': (bxc, byc - bh / 2.0), 'kind': kind}


def _draw_anchor(shapes: list, body, members: list, pos: dict, pal: dict,
                 font: str | None, quad: list, *, here: bool = False) -> dict:
    """在一处地块的**子四边形**里画要地：主楼（实心）+ 院子（空心）+ 名字。

    ★ 与 `_draw_compound` 是**同一套层序**（地块轮廓 / 空心院子 / 实心主楼），
      区别只在坐标来自 `quad` 的参数区间（`sub_quad`）而不是"以主体为中心外扩"。
      两套都留着是因为：地块图里要地必须落在地块内；而在"非城市尺度"
      （比如一张单独的院落图）没有地块可落，仍要用中心式。
    ★ 朝向跟随地块 ⇒ 用户说的"太横平竖直"在这一层也解决了。
    [EN] Draw a named building inside a **sub-quad of its parcel**: main building (filled) + yards
    [EN] (hollow) + name. ★ Same layer order as `_draw_compound` (parcel outline / hollow yards /
    [EN] filled main building); the only difference is that coordinates come from `quad`'s parameter
    [EN] ranges rather than "inflate around the body". Both exist because a named building in a parcel
    [EN] must stay inside the parcel, while at a non-city scale (a standalone courtyard plan) there is
    [EN] no parcel to sit in and the centred version is right. ★ Orientation follows the parcel, which
    [EN] also answers "too rectilinear" at this layer.
    """
    paper = pal.get('paper', '#f8f4ea')
    edge = pal.get('ink', '#4a4f57')
    col = pal.get('here', '#b23028') if here else edge
    kind = str(getattr(body, 'shape', '屋') or '屋')
    nm = str(getattr(body, 'name', '') or '')

    # ① 地块轮廓（这一处院落的范围）
    els = [fcv.Path.MoveTo(quad[0][0], quad[0][1])]
    els += [fcv.Path.LineTo(p[0], p[1]) for p in quad[1:]]
    els.append(fcv.Path.Close())
    shapes.append(fcv.Path(els, paint=ft.Paint(
        color=_mix(paper, edge, 0.34), stroke_width=1.0, style=ft.PaintingStyle.STROKE)))

    # ② 院子（空心=露天）：铺在地块靠街的那半，主楼压在它上面
    yards = [m for m in members if _is_open(m)]
    yard_q = sub_quad(quad, 0.06, 0.94, 0.06, 0.88)
    shapes.append(_fill_path(yard_q, _mix(paper, pal.get('wall', '#b9b1a0'), 0.06)))
    shapes.append(_stroke_path(yard_q, _mix(paper, edge, 0.38), 0.9))

    # ③ 主楼（实心）：**就是** `place_anchors` 给的那块（含 size 分档后的尺寸）。
    #   ⚠ 第一版在这里又写死 0.56 的比例，于是 size 分档被这一层吃掉：
    #     「特大」的大庙只比「小」的小庙宽 5%（实测 32.1 vs 30.5），分档形同虚设。
    # [EN] ③ The main building **is** the sub-quad from `place_anchors` (already sized by `size`).
    # [EN] ⚠ The first version hard-coded another 0.56 ratio here, which ate the size tiers: a "huge"
    # [EN] temple came out only 5% wider than a "small" shrine (32.1 vs 30.5 measured).
    body_q = sub_quad(quad, 0.04, 0.96, 0.06, 0.94)
    shapes.append(_fill_path(body_q, _mix(paper, col, 0.72)))
    shapes.append(_stroke_path(body_q, col, 1.0))

    # ④ 类型记号（寺/塔/观 加一个尖顶，只加记号不改轮廓）
    if any(k in nm for k in ('寺', '塔', '观', '庙', '阁')) or kind == '塔':
        cx = sum(p[0] for p in body_q) / 4.0
        cy = sum(p[1] for p in body_q) / 4.0
        top = min(p[1] for p in body_q)
        shapes.append(fcv.Path(
            [fcv.Path.MoveTo(cx - 4.0, top - 1.0),
             fcv.Path.LineTo(cx, top - 7.0),
             fcv.Path.LineTo(cx + 4.0, top - 1.0)],
            paint=ft.Paint(color=col, stroke_width=1.3, style=ft.PaintingStyle.STROKE)))

    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return {'box': (min(xs), min(ys), max(xs), max(ys)),
            'label_at': (sum(xs) / 4.0, min(ys)), 'kind': kind}


def _fill_path(quad: list, color: str) -> 'fcv.Path':
    """把四边形画成填充 Path。 English: render a quad as a filled Path."""
    els = [fcv.Path.MoveTo(quad[0][0], quad[0][1])]
    els += [fcv.Path.LineTo(p[0], p[1]) for p in quad[1:]]
    els.append(fcv.Path.Close())
    return fcv.Path(els, paint=ft.Paint(color=color, style=ft.PaintingStyle.FILL))


def _stroke_path(quad: list, color: str, width: float) -> 'fcv.Path':
    """把四边形画成描边 Path。 English: render a quad as a stroked Path."""
    els = [fcv.Path.MoveTo(quad[0][0], quad[0][1])]
    els += [fcv.Path.LineTo(p[0], p[1]) for p in quad[1:]]
    els.append(fcv.Path.Close())
    return fcv.Path(els, paint=ft.Paint(color=color, stroke_width=width,
                                        style=ft.PaintingStyle.STROKE))


def _is_open(p) -> bool:
    """这处是**露天**的吗（院子/天井/井台）—— 给它画空心。

    ★ 用名字判（含院/天井/庭/露台/晒/井台），与 `compounds` 的归属判据同源，
      不另写第三套词表。
    [EN] Is this place **open to the sky** (yard / patio / well terrace) -- drawn hollow? ★ Judged by
    [EN] name (院/天井/庭/露台/晒/井台), the same source as `compounds`' assignment rule, so no third
    [EN] word list.
    """
    n = str(getattr(p, 'name', '') or '')
    return any(k in n for k in ('院', '天井', '庭', '露台', '晒', '井台'))


def _feature_symbol(shapes: list, shape: str, x: float, y: float, r: float,
                    pal: dict, *, here: bool = False) -> None:
    """导览图里的**地物分类符号**（屋/院/桥/渡/塔/寺…各一个记号）。

    ★ 为什么按类型画符号而不是一律圆点：导览图上"这是什么地方"是第一信息。
      一个圆点只能表达"这里有东西"，表达不了"这是桥还是寺"。
    ★ 符号形状刻意用**最省的区别**：方块=人工物、开口方块=院落、双横=桥、
      三角=山、竖线+顶=塔、菱形=市集。**闭集内一一对应**，图例也照这个画。
    ⚠ 不追求"像真的"：这是示意图，真实轮廓我们没有（也不该编）。
    [EN] The **classified feature symbol** for a guide map (one mark per kind: house / yard / bridge /
    [EN] ferry / tower / temple...). ★ Why typed symbols instead of uniform dots: on a guide map "what
    [EN] kind of place is this" is the primary information; a dot says "something is here" but not
    [EN] "a bridge or a temple". ★ The shapes use the cheapest distinctions: square = built, open square
    [EN] = yard, double line = bridge, triangle = hill, stem with a cap = tower, diamond = market --
    [EN] one-to-one inside a closed set, and the legend draws the same marks. ⚠ Not chasing realism:
    [EN] this is schematic, and we have no true outlines (nor should we invent them).
    """
    col = pal.get('here', '#b23028') if here else pal.get('ink', '#4a4f57')
    s = max(2.2, float(r))
    if shape in ('院',):
        # 院落：开口方框（缺口朝下，表示"门在这一面"）
        shapes.append(fcv.Path(
            [fcv.Path.MoveTo(x - s, y + s * 0.75), fcv.Path.LineTo(x - s, y - s),
             fcv.Path.LineTo(x + s, y - s), fcv.Path.LineTo(x + s, y + s * 0.75)],
            paint=ft.Paint(color=col, stroke_width=1.4,
                           style=ft.PaintingStyle.STROKE)))
    elif shape in ('桥',):
        # 桥：两道平行短横（桥面 + 栏杆）
        for dy in (-s * 0.32, s * 0.32):
            shapes.append(fcv.Line(x - s * 1.25, y + dy, x + s * 1.25, y + dy,
                                   paint=ft.Paint(color=col, stroke_width=1.6,
                                                  stroke_cap=ft.StrokeCap.ROUND)))
    elif shape in ('渡',):
        # 渡口：三道渐短的横线（水纹）＋ 一条竖杆
        for k, dy in enumerate((-s * 0.55, 0.0, s * 0.55)):
            hw = s * (1.15 - 0.22 * k)
            shapes.append(fcv.Line(x - hw, y + dy, x + hw, y + dy,
                                   paint=ft.Paint(color=col, stroke_width=1.2,
                                                  stroke_cap=ft.StrokeCap.ROUND)))
    elif shape in ('山',):
        shapes.append(fcv.Path(
            [fcv.Path.MoveTo(x, y - s), fcv.Path.LineTo(x + s, y + s * 0.8),
             fcv.Path.LineTo(x - s, y + s * 0.8), fcv.Path.Close()],
            paint=ft.Paint(color=col, stroke_width=1.2,
                           style=ft.PaintingStyle.STROKE)))
    elif shape in ('塔',):
        # 塔/楼阁：竖杆 + 顶盖
        shapes.append(fcv.Line(x, y - s * 0.2, x, y + s,
                               paint=ft.Paint(color=col, stroke_width=1.8,
                                              stroke_cap=ft.StrokeCap.ROUND)))
        shapes.append(fcv.Path(
            [fcv.Path.MoveTo(x - s * 0.85, y - s * 0.2),
             fcv.Path.LineTo(x, y - s * 1.05),
             fcv.Path.LineTo(x + s * 0.85, y - s * 0.2)],
            paint=ft.Paint(color=col, stroke_width=1.5,
                           style=ft.PaintingStyle.STROKE)))
    elif shape in ('市',):
        # 市集：菱形
        shapes.append(fcv.Path(
            [fcv.Path.MoveTo(x, y - s), fcv.Path.LineTo(x + s, y),
             fcv.Path.LineTo(x, y + s), fcv.Path.LineTo(x - s, y), fcv.Path.Close()],
            paint=ft.Paint(color=col, stroke_width=1.4,
                           style=ft.PaintingStyle.STROKE)))
    elif shape in ('树',):
        shapes.append(fcv.Circle(x, y, s * 0.85, paint=ft.Paint(
            color=col, stroke_width=1.2, style=ft.PaintingStyle.STROKE)))
        shapes.append(fcv.Circle(x, y, s * 0.3, paint=ft.Paint(
            color=col, style=ft.PaintingStyle.FILL)))
    elif shape in ('亭', '台', '门'):
        # 亭/台/门：空心小方（"人工构筑物"的通用记号）
        shapes.append(fcv.Rect(x - s * 0.9, y - s * 0.9, s * 1.8, s * 1.8,
                               border_radius=1.0,
                               paint=ft.Paint(color=col, stroke_width=1.4,
                                              style=ft.PaintingStyle.STROKE)))
    else:
        # 屋（默认）：实心小方 —— 最"普通的一处人工物"
        shapes.append(fcv.Rect(x - s * 0.8, y - s * 0.8, s * 1.6, s * 1.6,
                               border_radius=1.0,
                               paint=ft.Paint(color=col,
                                              style=ft.PaintingStyle.FILL)))


def build_city_shapes(shapes: list, layout, places: list, px, *,
                      pal: dict, font: str | None = None,
                      span: tuple | None = None,
                      current: str = '',
                      style=None,
                      blocks: bool | None = None) -> dict:
    """在 `shapes` 上画一张**城市图**（高德那种：面是街区、线是分级路、点是 POI）。

    Args:
        shapes: 目标图元列表（就地追加）。
        layout: `map_layout.Layout`（读 `links` / `water` / `walls`）。
        places: 地点（`Place`）列表。
        px: `Place -> (x, y)` 的像素换算（与室内图**共用同一份**，别另算）。
        pal: 调色板（`floorplan.PALETTE`）。
        span: 绘图区 `(x0, y0, x1, y1)`；不给就从 `places` 的外接框外扩。
        current: 当前地点名（朱砂 + 加粗）。

    ## 画法（顺序 = 图层叠放，后画的压在上面）

    1. **水系面**：`water` 折线加宽成带（先在底下，让路压在上面）；
    2. **街区面**：Voronoi 切出来的地块，浅填充 + **细描边** —— 这是"高德感"的来源：
       读者一眼看到"这里被路分成了几块"；
    3. **路网**：`links` 逐条画，宽度按**两端规模**取（大-大 最宽），
       双线（外宽内纸）—— 单线看着是"一条线"，双线才是"一条路"；
    4. **POI**：地点不再画成"斜纹小方块"（那是**建筑**的记号，城市图里一栋栋画会糊成一片），
       改成**圆点 + 分级字号**；当前地点用朱砂。
    5. **名字避让**：用 `label_place.place_label`，不与别的名字/圆点重叠（用户点过这一条）。

    ★ 街区怎么切**由建筑传统决定**（`Style.路网`）：棋盘／环形放射／自然生长。
      三者的共同底线是"边界只落在两处地点的中点（或方位/半径中点）"——
      **不凭空画一层等距网格**：那才是编出来的路。
    ★ 为什么路宽按两端规模：不给真实路宽（我们不知道），但"通往大地方的宽、通往
      小地方的窄"是可读且**不会编**的相对信息。

    [EN] Draw a **city map** (Gaode-like: areas are blocks, lines are graded roads, points are
    [EN] POIs). Layer order matters: water band first, then Voronoi blocks with thin outlines (the
    [EN] "map feel" comes from seeing that roads split the area into blocks), then roads as double
    [EN] lines whose width follows the **size of both endpoints**, then POIs as dots with graded
    [EN] labels (a building block per place would smear into a mess at this scale), then labels with
    [EN] collision avoidance. ★ Blocks are Voronoi, not a grid, because a grid is "roads invented out
    [EN] of nothing" while a Voronoi edge sits exactly between two landmarks -- which is how city
    [EN] blocks are actually divided. ★ Road width follows endpoint size: we do not know real
    [EN] widths, but "wide towards big places" is readable and **not invented**.
    """
    if not places:
        return {'roads': [], 'greens': [], 'waters': False, 'pois': 0, 'blocks': 0,
                'net': NET_ORGANIC, 'walls': False, 'mode': CITY_AREA,
                'features': [], 'compounds': [],
                'massing': 0, 'massing_rects': [], 'blocks_poly': []}
    pos = {p.name: px(p) for p in places}
    box = span or _auto_span(pos)
    net = net_of(style)
    # ★★★ 2026-10-27：**街区还是导览**由地点密度决定（见 `city_mode` 的说明）。
    #   这是"一摞长方形"那个报障的修法：6 处地物不该被切成 6 个条形地块。
    # [EN] ★★★ 2026-10-27: **blocks or guide** is decided by place density (see `city_mode`). This is
    # [EN] the fix for the "stack of rectangles" report: six features must not be carved into six
    # [EN] stripy parcels.
    mode = CITY_BLOCKS if (blocks is True or (blocks is None and city_mode(places) == CITY_BLOCKS)) \
        else CITY_AREA
    # ★ 2026-10-26：把"这张图上真画了什么"记下来，交给图例。
    #   图例**只列出现过的符号**（列了没出现的，读者会去找"那条运河在哪"）。
    # [EN] ★ 2026-10-26: record what this map actually drew, for the legend. The legend lists **only
    # [EN] symbols that appear** (listing absent ones sends the reader hunting for them).
    info = {'roads': [], 'greens': [], 'waters': bool(len(getattr(layout, 'water', None) or []) >= 2),
            'pois': len(places), 'blocks': 0, 'net': net, 'walls': False,
            'mode': mode, 'features': [], 'compounds': [],
            'massing': 0, 'massing_rects': [], 'blocks_poly': [],
            # 水系类型（`river`/`lake`/`coast`），图例按它写"河流/湖/海域"
            # [EN] Water kind (river/lake/coast); the legend words itself from it
            'water_kind': ''}

    # ① 水系：**按类型分三路**（河=带 / 湖=闭合填充 / 海=海域面+海岸线）
    # [EN] 1. Water: **routed by kind** (river = band / lake = filled outline / sea = area + coastline)
    #
    # ★★★ 2026-10-27：这一段原来固定"居中加粗 22px + 棕岸 + 再补一层蓝面"（三层，顺序混乱，
    #   靠后画的盖前画的来救）。对河正确；**对海完全不对** —— 居中的带把海往陆地推半个带宽，
    #   而且海那一面没有任何填充 ⇒ 图上变成"沿着海岸有一条蓝色的河"。
    #   现在交给 `draw_water()`（城市图与城际图**共用这一份实现**，只有 `band` 不同）。
    # [EN] ★★★ 2026-10-27: this used to be a fixed "centre-thickened 22px band + brown bank + one
    # [EN] more blue pass" (three layers in a confusing order, fixed by later passes painting over
    # [EN] earlier ones). Right for a river, **wrong for the sea**: a centred band pushes the sea half
    # [EN] a bandwidth inland and leaves it unfilled, so the map showed "a blue river along the coast".
    # [EN] Now delegated to `draw_water()` -- **one implementation shared with the region map**, which
    # [EN] differs only in `band`.
    _wt = draw_water(shapes, layout, px, pal, box, band=22.0, places=places)
    if _wt.get('kind'):
        # ⚠ **只记类型，不要动 `info['waters']`**：两个渲染器里这个键的语义不同 ——
        #   城市图是 `bool`（"这张图有水吗"），城际图是**列表**（水体符号的坐标）。
        #   第一版统一写成 `bool(...)`，城际图当场崩在 `info['waters'].append(...)`。
        # [EN] ⚠ **Only record the kind; do not touch `info['waters']`**: that key means different
        # [EN] things in the two renderers -- a `bool` in the city map ("does this map have water")
        # [EN] and a **list** of water-symbol positions in the region map. The first version wrote a
        # [EN] `bool(...)` to both and the region map crashed on `info['waters'].append(...)`.
        info['water_kind'] = _wt['kind']
        # ★ 渲染层**自己记**"画了多大一片水"：判据读它，不要从图元反推
        #   （城市图上街区、建筑都是填充面，靠"数填充面"分不出哪片是水 —— 实测 S1 误抓 61 个）。
        # [EN] The renderer **records** how much water area it drew; criteria read it instead of
        # [EN] inferring semantics from primitives (blocks and buildings are filled faces too, so
        # [EN] "count the filled faces" cannot tell which one is water -- S1 caught 61 false ones).
        info['water_poly'] = _wt.get('sea') or _wt.get('lake') or []
        info['coast_line'] = _wt.get('coast') or []

    # ② 街区面：**形态由建筑传统决定**（棋盘 / 环形放射 / 自然生长）
    # [EN] 2. Blocks: form decided by the building tradition (grid / radial / organic)
    #
    # ★★★ 2026-10-26：这一段原来只有一种切法（Voronoi），于是**所有世界的地图长得一样**。
    #   现在按 `worldstyle.Style.路网` 分三路（`net_of`）：
    #     grid   → 一维 Voronoi 的乘积 ⇒ 矩形街区（横直街划分，坊市制都城）
    #     radial → 极坐标 Voronoi     ⇒ 环形＋扇形的街区（环形城／空间站）
    #     organic→ 二维 Voronoi       ⇒ 自然生长的分片（沿街沿路的城镇）
    #   ⚠ 三者**都不是编的**：边界一律落在两处地点的中点/方位中点/半径中点，
    #     也就是"这一片归近的那个地方"——同一个语义，三种坐标系。
    # [EN] ★★★ 2026-10-26: this block had one tessellation only (Voronoi), so **every world's map
    # [EN] looked the same**. Now `worldstyle.Style.路网` picks one of three (`net_of`): grid => the
    # [EN] product of two 1-D Voronoi cuts (rectilinear blocks, the ward-market capital); radial =>
    # [EN] a polar Voronoi (rings and wedges, ring cities and stations); organic => 2-D Voronoi.
    # [EN] ⚠ None of them is fabricated: every boundary falls at a midpoint between two places --
    # [EN] "this patch belongs to the nearer one", one meaning in three coordinate frames.
    #
    # ★★★ 2026-10-27：**导览模式一个街区都不画**（`mode == CITY_AREA`）。
    #   地点只有 6 处时，切出来的 6 块是长宽比 2~3 的条形，紧贴着拼满画框 ——
    #   用户看到的就是"一摞长方形"。导览图改为：地物**分类符号 + 地名**，路照画。
    #   ⚠ 这是"少画一层"而不是"多画一层"：删掉的正是没有数据支撑的那层。
    # [EN] ★★★ 2026-10-27: **guide mode draws no blocks at all** (`mode == CITY_AREA`). With six
    # [EN] places the cells come out as strips of aspect 2-3 tiling the frame edge to edge -- exactly the
    # [EN] "stack of rectangles" the user saw. Guide mode instead draws **classified feature symbols
    # [EN] plus names**, keeping the roads. ⚠ This removes a layer rather than adding one: what goes is
    # [EN] the layer with no data behind it.
    # ★★★ 2026-10-27（用户：「地图中道路穿越建筑了 这不合理」）：
    #   **先定路，再切街区** —— 街区必须被道路"切开"，而不是道路从街区上压过去。
    #
    #   病根：街区是 Voronoi 细分出来的实心面（还带描边，视觉上就是一栋栋建筑），
    #   而道路是两地点之间的连线，其中斜的那条必然穿过若干街区块。
    #   在标准地图上，街区本来就是**被道路切出来的地块** —— 顺序反了，
    #   所以"路压在建筑上"。这里把顺序纠正过来：
    #     ① 先把所有路段算出来（含棋盘的直角折点）——**只算一次**，后面画路复用同一份；
    #     ② 每条路段把它附近的街区**切开并退让**（`_carve_roads`）；
    #     ③ 剩下的才是街区。
    #   ⚠ 路段只算一次是关键：如果切街区用一份、画路用另一份，"路"与"街区的缝"就会错位，
    #     表现是"路仍压在街区边上"——本项目"两处实现必然漂"的老坑。
    # [EN] ★★★ 2026-10-27 (the user: "roads cut through buildings on the map, that is unreasonable"):
    # [EN] **decide the roads first, then cut the blocks** -- blocks must be *cut by* roads, not have
    # [EN] roads run over them. Root cause: blocks were solid Voronoi parcels (with an outline, i.e.
    # [EN] visually a row of buildings) while roads are lines between places, so the slanted one
    # [EN] necessarily crossed several parcels. On a standard map a block **is the ground cut out by the
    # [EN] roads** -- the order was reversed, hence "roads on top of buildings". Fixed here: (1) compute
    # [EN] all road segments first (including the grid mode's right-angle corners) -- **once**, reused
    # [EN] when drawing; (2) each segment **splits and pushes back** nearby blocks (`_carve_roads`);
    # [EN] (3) what remains is the blocks. ⚠ Computing the segments once matters: carving with one set
    # [EN] and drawing with another would misalign road and gap, i.e. "the road still sits on the block
    # [EN] edge" -- this project's classic "two implementations always drift".
    # ★★★ 2026-10-27（用户，第四条重话）：路**不再**是"两处地点之间的连线"。
    #
    #   > 「其中的道路正常画 而不是直接连接几个目标建筑 真正地图中 是不会出现这样的直连道路的，
    #   >   主角所在建筑也只是城市街道中的普通一员」
    #
    #   原来 `road_segs = _city_road_segs(...)` 把 `layout.links`（一个**可达关系**：
    #   "这两处之间走得到"）直接画成直线。后果有两层，都是错的：
    #     ① 图上是"从 A 拉到 B"的斜直线，真实地图没有这种路；
    #     ② 所有路都汇聚到那几处有名字的地方 ⇒ 主角楼成了路网枢纽，
    #        而真实城市里它只是街上的一户。
    #
    #   ⇒ 现在路网由 `streetnet()` 独立生成（街距、方位角、形态），**完全不看地点**；
    #     地点只决定"哪块地块上画一栋有名字的要地"。街区 = 街网围出的地块。
    #     这样"路穿越建筑"在结构上也不可能（地块是路围出来的），不需要事后检测。
    #   ⚠ 路段仍只算**一次**：`streetnet` 的折线拆成段给绘制用，地块也从同一次调用出。
    # [EN] ★★★ 2026-10-27 (the user's fourth hard note): roads are **no longer** "lines between two
    # [EN] places". The old `_city_road_segs` drew `layout.links` -- a **reachability relation** -- as
    # [EN] straight lines, which is wrong twice over: (1) the map showed "A to B" diagonals that no real
    # [EN] map has; (2) every road converged on the few named places, making the protagonist's house a
    # [EN] network hub, while in a real town it is one household on a street. => The network now comes
    # [EN] from `streetnet()` (spacing, bearing, form) and **never looks at places**; a place only
    # [EN] decides which parcel carries a named building, and blocks are the parcels the network
    # [EN] encloses. "Roads through buildings" is then impossible by construction, with no later check.
    # [EN] ⚠ Segments are still computed **once**: the polylines are flattened for drawing, and the
    # [EN] parcels come from the same call.
    _net_doc = streetnet(box, net=net)
    road_segs: list = []
    for _pts, _cls in (_net_doc['roads'] + _net_doc['lanes']):
        for _k in range(len(_pts) - 1):
            road_segs.append((_pts[_k], _pts[_k + 1], _cls))
    cells: list = []
    if mode == CITY_BLOCKS:
        # 地块**本身**就是街网围出来的面；只内缩一点点，让街道有可见宽度。
        # ⚠ 不内缩 5px（那是 Voronoi 时代为了把共享边界拉开）：现在街宽由街距体现，
        #   内缩多了会让街区缩成一小块，四周留白像空地。
        # [EN] The parcels **are** the faces enclosed by the network; inset only slightly so the street
        # [EN] has visible width. ⚠ Not 5px (that was for pulling shared Voronoi edges apart): street
        # [EN] width now comes from the spacing, and a large inset shrinks blocks into empty ground.
        # ⚠ **不再二次内缩**：`streetnet` 的 lots 已经按**每条街的半宽**退让过了。
        #   再缩 1.5px 是重复动作，而且会把边缘地块缩小到"碎屑"以下（实测 380 → 267），
        #   于是"没有碎屑地块"那条判据永远红。**内缩只许有一处实现。**
        # [EN] ⚠ **No second inset**: `streetnet`'s lots have already retreated by **each street's
        # [EN] half-width**. Insetting another 1.5px is redundant and shrinks edge parcels below the
        # [EN] sliver threshold (measured 380 -> 267), so "no sliver parcels" could never pass.
        # [EN] **One inset, one implementation.**
        cells = list(_net_doc['lots'])
    info['blocks'] = len(cells)
    info['blocks_poly'] = [[(round(x, 1), round(y, 1)) for x, y in c] for c in cells]
    info['lanes'] = len(_net_doc['lanes'])
    info['bearing'] = round(float(_net_doc['bearing']) * 57.2958, 1)

    # ★★★ 2026-10-27：三层要分开 —— 地面（街区）/ 无名建筑体量 / 有名字的要地。
    #
    #   顺序仍是"路 → 地块 → 建筑"：建筑排在**地块**里，而地块是街围出来的，
    #   所以它天然不可能压到路上（靠顺序，不靠事后检测）。
    #   要地（有名字的建筑）**先**定位到某个地块里，再排无名建筑并让开它 ——
    #   否则会出现"要地压在一排无名房子上"。
    # [EN] Three layers must separate: ground (blocks) / anonymous massing / named compounds. The
    # [EN] order is still "roads -> parcels -> buildings": buildings sit in parcels, and parcels are
    # [EN] enclosed by streets, so they cannot overlap a road by construction. Named compounds are
    # [EN] **placed first**, then the massing keeps clear of them -- otherwise a named building would
    # [EN] end up on top of a row of anonymous houses.
    groups, marks = compounds(places, style)
    anchors: list = []                 # 要地：(主体, 成员, 四边形)
    mass: list = []
    if mode == CITY_BLOCKS and cells:
        anchors = place_anchors(groups, pos, cells)
        avoid: list = [aq for (_b, _m, aq) in anchors]
        for m in marks:
            mxx, myy = pos[m.name]
            avoid.append([(mxx - 7.0, myy - 7.0), (mxx + 7.0, myy - 7.0),
                          (mxx + 7.0, myy + 7.0), (mxx - 7.0, myy + 7.0)])
        for _i, poly in enumerate(cells):
            mass.extend(row_buildings(poly, avoid=avoid, seed=_i))
    info['massing'] = len(mass)
    # ⚠ 存**四边形**（不是包围盒）：建筑现在带方位角，用 xyxy 存会把方向信息丢掉，
    #   判据也就看不出"是不是轴对齐"。
    # [EN] ⚠ Store **quads** (not bounding boxes): buildings now carry a bearing, and xyxy would throw
    # [EN] the orientation away -- the criterion could then no longer tell axis-aligned from not.
    info['massing_rects'] = [[[round(p[0], 1), round(p[1], 1)] for p in q] for q in mass]
    # ★★★ 2026-10-27：街区的**视觉要弱**。它表示"地面"，不是"物体"：
    #   原来 0.10 的填充 + 0.22 的描边，看起来就是一排排建筑（正是用户说"道路穿越建筑"的前提 ——
    #   他把街区块当成建筑看了）。标准地图上街区只是比底色略深的一片地面，边界几乎看不见。
    # [EN] ★★★ 2026-10-27: the blocks' **visual weight must be low**. A block is *ground*, not an
    # [EN] object: the old 0.10 fill + 0.22 outline looked like rows of buildings (which is exactly the
    # [EN] premise of "roads cut through buildings" -- the user read the parcels as buildings). On a
    # [EN] standard map a block is only slightly darker ground with an almost invisible edge.
    block_fill = _mix(pal.get('paper', '#f8f4ea'), pal.get('wall', '#b9b1a0'), 0.06)
    block_line = _mix(pal.get('paper', '#f8f4ea'), pal.get('ink', '#4a4f57'), 0.10)
    for poly in cells:
        els = [fcv.Path.MoveTo(poly[0][0], poly[0][1])]
        els += [fcv.Path.LineTo(x, y) for x, y in poly[1:]]
        els.append(fcv.Path.Close())
        shapes.append(fcv.Path(els, paint=ft.Paint(color=block_fill,
                                                 style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Path(els, paint=ft.Paint(color=block_line, stroke_width=0.8,
                                                 style=ft.PaintingStyle.STROKE)))
    # 街区里的无名建筑（画在街区之上、道路与地物之下）
    # [EN] Anonymous buildings inside the blocks (above the parcels, below roads and features)
    _draw_massing(shapes, mass, pal)

    # ③ 路网：分级双线
    # [EN] 3. Road network: graded double lines
    #
    # ★★★ 2026-10-26（用户）：「如果是室外地图 按照标准地图画法绘制道路等所有元素」
    #   标准地图的道路有**等级体系**，不是"手感宽度"。三档（`scale.road_class`）：
    #     trunk 主干道 → 双线带 + **中心线**（标准地图上主通道才画中线）
    #     main  次干道 → 双线带
    #     local 支路   → 细双线
    #   分级与画法参数都在 `scale.py` 一处定义，城际图共用同一份 —— 同一份 `links`
    #   在两张图上必须粗细**成比例**，否则读者会以为它们画的是不同的路网。
    #   ⚠ 不画路名与编号：我们没有路网表，编一个"国道 305"就是假信息。
    #   ⚠ 不画"高速公路"这一档：那需要真实的等级数据，推不出来。
    #
    # ★ 交叉口处理：标准地图的双线在路口处**汇成一个面**，不是两条线互相压着。
    #   ★★★ 2026-10-27（用户：「大地图里街道之间交叉的地方不要加圆圈了」）：
    #   原来的做法是在节点处画一个"路面圆"（与内芯同色），双线自然收进圆里。
    #   那个圆的半径是**写死**的（6px），跟路宽毫无关系 ⇒ 支路上那个圆比路本身还宽、
    #   **探到路外**，整张图上每个交叉点都鼓出一个白圆饼。
    #   ⇒ 现在改为**分档分两遍**画：同一档先把所有路的**外框**画完，再画所有路的**内芯**；
    #     交叉处是"内芯压内芯"⇒ 路面自然并成一块，双线在路口断开（标准地图的画法）。
    #     按**等级**从窄到宽一档一档画 ⇒ 粗街的路缘连续，细街汇到粗街边上就停。
    #
    # ★★ 棋盘路网里路走**直角**（2026-10-26 加）：街区的边是横平竖直的，路若斜穿过去
    #   就"路把街区切开了"—— 那是自相矛盾。棋盘城市里两点之间本来就只能横走再竖走。
    #   街区边界正好落在两处地点的中点 ⇒ 直角折点落在边界上，路与街区对得上。
    # [EN] ★★★ 2026-10-26 (the user): "if it is an outdoor map, draw roads and all other elements
    # [EN] following standard cartographic conventions." Roads on a standard map form a **hierarchy**,
    # [EN] not a hand-tuned width. Three classes (`scale.road_class`): trunk => double band + **centre
    # [EN] line** (only main arteries carry one on a real map); main => double band; local => thin
    # [EN] double. Class and drawing parameters are defined once in `scale.py` and shared with the
    # [EN] region map -- the same `links` must scale proportionally on both maps, or the reader thinks
    # [EN] they are different networks. ⚠ No road names or numbers: we have no network table and
    # [EN] inventing "National Route 305" is false information. ⚠ No "motorway" class: that needs real
    # [EN] classification data and cannot be inferred. ★ Junctions: on a real map the double lines
    # [EN] **merge into one surface** at a junction instead of crossing. ★★★ 2026-10-27 (the user:
    # [EN] "don't put circles where streets cross"): the old rendering put a "road surface" disc at
    # [EN] each node, with a **hard-coded** 6px radius unrelated to the road width -- on a lane the
    # [EN] disc was wider than the road and spilled outside it, so every crossing bulged a white
    # [EN] blob. => Now drawn **by class, two passes per class**: all casings of that class, then all
    # [EN] cores of that class => core over core at a crossing, so the surface merges and the double
    # [EN] lines break there (standard cartography). Classes narrow-first => a wide road's edge lines
    # [EN] stay continuous and narrow roads join them. ★★ In grid mode roads turn at **right angles**:
    # [EN] block edges are axis-aligned, and a diagonal road would *cut a block in half*, which is
    # [EN] self-contradictory. In a grid city you travel across, then up.
    # ★★★ 2026-10-27：**这一段只负责画**，路段已经在前面算好（`road_segs`）。
    #   为什么要拆开：街区必须**被路切开**，所以切街区之前就得知道路段；
    #   若切街区用一份、画路用另一份，"路"与"街区缝"的位置就会漂 ——
    #   表现是"路仍贴着街区边"（本项目"两处实现必然漂"）。
    #   现在只有 `_city_road_segs` 一处定义路段，绘制与切块共用同一份列表。
    # [EN] ★★★ 2026-10-27: **this block only draws**; the segments were computed earlier
    # [EN] (`road_segs`). Why split: blocks must be **cut by** the roads, so the segments must exist
    # [EN] before carving; carving with one set and drawing with another would let road and gap drift,
    # [EN] i.e. "the road still hugs the block edge". Now `_city_road_segs` is the single definition and
    # [EN] both carving and drawing consume the same list.
    # ★★★ 2026-10-27（用户）：「大地图里街道之间交叉的地方不要加圆圈了」。
    #
    #   原来每个路口节点都补一个**半径 6px 的圆**（纸色）当"路面"，
    #   于是整张图上每个交叉点都鼓出一个白圆饼 —— 那不是路口的样子，
    #   而且圆的半径是写死的，跟路宽无关：支路（内芯 3.6）窄，6px 的圆比路还宽，
    #   于是圆**探到路外**，看起来像"路口上放了个圆盘"。
    #
    #   ⇒ 改用**标准地图的路口画法**：路面在路口处**并成一块**，不靠补圆。
    #     做法是**分档分两遍**画：
    #       ① 先把这一档所有路的**外框**（墙色）画一遍；
    #       ② 再把这一档所有路的**内芯**（纸色）画一遍。
    #     同档的两条街交叉时，内芯压内芯 ⇒ 路面自然合成一块（十字形），
    #     外框留在外圈 ⇒ 路口处的双线**断开**，这正是标准地图上路口的样子。
    #     按**等级**从窄到宽一档一档画：粗街后画 ⇒ 粗街的路缘连续，
    #     细街汇到粗街边上就停（不会被粗街的路面切断）。
    #   ⚠ 顺序别写成"所有外框 → 所有内芯"：那样细街的内芯会**切断粗街的路缘**。
    # [EN] ★★★ 2026-10-27 (the user): "in the big map, don't put circles where streets cross".
    #   Every junction used to get a **6px paper disc**, so each crossing bulged a white blob --
    #   and the radius was hard-coded, unrelated to the road width: on a lane (3.6 core) the disc is
    #   wider than the road and **spills outside** it, reading as "a plate dropped on the junction".
    #   => Use the **standard cartographic junction**: the surfaces **merge into one** at the
    #   crossing, no patch disc. Draw **by class, two passes per class**: (1) all casings of that
    #   class, (2) all cores of that class. Two streets of the same class crossing => core over core
    #   => the surface merges into a cross, the casings stay outside => the double lines **break** at
    #   the junction, which is what a junction looks like on a real map. Classes are drawn **narrow
    #   first**, so a wide road's edge lines stay continuous and the narrow road joins them.
    #   ⚠ Do **not** write it as "all casings, then all cores": that lets a lane's core cut through
    #   a main road's edge line.
    _by_cls: dict = {}
    for (a, b, cls) in road_segs:
        info['roads'].append(cls)
        _by_cls.setdefault(cls, []).append((a, b))
    for _cls in sorted(_by_cls, key=lambda c: SC.ROAD_SPEC.get(c, (0.0, 0.0, False))[0]):
        _segs = _by_cls[_cls]
        for (_a, _b) in _segs:
            _road_seg(shapes, _a, _b, _cls, pal, layer='casing')
        for (_a, _b) in _segs:
            _road_seg(shapes, _a, _b, _cls, pal, layer='core')

    # ★ 城墙：**有数据才画**（`layout.walls` 是一圈闭合折线）。
    #   2026-10-26：中西古城的地图**最显眼的要素就是城墙**，而这里原来完全不读它。
    #   ⚠ 只读作者给的折线，**绝不"按地点外接框画一圈"** —— 那是凭空造一堵墙，
    #     而且墙的位置会决定读者对城门、对城内外的所有判断。
    # [EN] City wall: **only when the data has one** (`layout.walls` is a closed polyline).
    # [EN] 2026-10-26: the wall is the most prominent element of a pre-modern city map, and this
    # [EN] code never read it. ⚠ Only the author's polyline, **never a ring around the bounding
    # [EN] box** -- that would invent a wall, and its position decides everything the reader infers
    # [EN] about gates and inside/outside.
    _walls = list(getattr(layout, 'walls', None) or [])
    if len(_walls) >= 3:
        pts = [px(_P(a, b)) for a, b in _walls]
        els = [fcv.Path.MoveTo(pts[0][0], pts[0][1])]
        els += [fcv.Path.LineTo(x, y) for x, y in pts[1:]]
        els.append(fcv.Path.Close())
        shapes.append(fcv.Path(els, paint=ft.Paint(
            color=pal.get('ink', '#4a4f57'), stroke_width=7.0,
            stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
        shapes.append(fcv.Path(els, paint=ft.Paint(
            color=pal.get('paper', '#f8f4ea'), stroke_width=4.0,
            stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
        info['walls'] = True

    # ★ 绿地：**名字能判的才画**（公署/公园/花园/林/草坪/广场/园）。
    #   不按"看起来像绿地"去猜 —— 猜出来的绿地把读者的方位感带偏，比不画更坏。
    #   标准地图的绿地向来只依赖"这里确实是绿地"这个事实。
    # [EN] Green space: **drawn only when the name says so** (公园/花园/林/草坪/广场/园). Never
    # [EN] guessed from "looks green" -- a invented park misleads the reader's sense of place worse
    # [EN] than drawing none. On real maps green space likewise depends on the fact, not a hunch.
    for p in places:
        if not _is_green(p.name):
            continue
        cx, cy = pos[p.name]
        r = 7.0 + 1.6 * SIZE_W.get(str(getattr(p, 'size', '中')), 2)
        shapes.append(fcv.Circle(cx, cy, r, paint=ft.Paint(
            color=_mix(pal.get('paper', '#f8f4ea'), '#6f9e5a', 0.45),
            style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Circle(cx, cy, r, paint=ft.Paint(
            color=_mix(pal.get('paper', '#f8f4ea'), '#3f6e34', 0.55),
            stroke_width=1.0, style=ft.PaintingStyle.STROKE)))
        info['greens'].append(p.name)

    # ④ 地物：**建筑按建筑群画轮廓**，独立地物画符号
    # [EN] 4. Features: **buildings as compound footprints**, standalone features as symbols
    #
    # ★★★ 2026-10-27（用户三条）：
    #   ①「院子 临河楼 后院井台 这几个都是属于临河楼的部分 为何被画到了不同建筑里」
    #      ⇒ 一组合成**一处**（`compounds`），院子画成空心、楼画成实心，共用一条地块轮廓；
    #   ②「建筑有一些三角和异形建筑 因为在现实中不太常见」
    #      ⇒ 轮廓只由**轴对齐矩形**拼（`_footprint_rect` / `_draw_compound`），没有三角形；
    #   ③「所有建筑大小都一样也不太合理」
    #      ⇒ 尺寸按 `Place.size` 分档，且**成员多的群更大**；独立地物的符号也按 size 变。
    #   ⚠ 街区（地块底纹）与建筑是两层：街区是"地面"，建筑是"地面的东西"。
    #     上一轮把街区画深了，用户就把街区当成了建筑 —— 所以街区保持极淡。
    # [EN] ★★★ 2026-10-27 (the user's three points): (1) "the courtyard, the building and the well
    # [EN] terrace all belong to that building -- why drawn as different buildings" => one compound
    # [EN] (`compounds`), the yard hollow, the building filled, sharing one parcel outline; (2) "some
    # [EN] buildings are triangles or odd shapes, uncommon in reality" => outlines are built only from
    # [EN] **axis-aligned rectangles**, no triangles; (3) "it is unreasonable that every building is the
    # [EN] same size" => sizes follow `Place.size`, a compound with more members is larger, and standalone
    # [EN] symbols scale by size too. ⚠ Blocks (the ground tint) and buildings are two layers: blocks are
    # [EN] *ground*, buildings are *things on the ground*. Last round the blocks were too dark and the
    # [EN] user read them as buildings -- so blocks stay very light.
    labels: list = []
    # ⚠ `groups/marks/anchors` 已在排建筑那一层算过（体量要让开它们），这里**复用**，不另算。
    # [EN] `groups/marks/anchors` were computed in the massing layer (massing must keep clear of
    # [EN] them); reused here rather than recomputed.
    for (body, members, _aq) in anchors:
        here = bool(current) and (body.name == current
                                  or any(m.name == current for m in members))
        got = _draw_compound(shapes, body, members, pos, pal, font, here=here,
                             quad=_aq)
        bx0, by0, bx1, by1 = got['box']
        # 名字写在**地块上方**（不在实心块上，免得字压在矩形里读不出）
        size = CITY_FONT.get(SIZE_W.get(str(getattr(body, 'size', '中')), 2), 11)
        disp = _disp(body)
        lw, lh = _est(disp, size)
        lx, ly = _place_label((bx0, by0, bx1, by1), lw, lh, labels, box)
        labels.append((lx, ly, lw, lh))
        shapes.append(MM._text(lx + lw / 2.0, ly, disp, size=size,
                               color=(pal.get('here', '#b23028') if here
                                      else pal.get('ink', '#4a4f57')),
                               font=font, center=True, bold=here))
        info['compounds'].append({
            '主体': body.name, '成员': [m.name for m in members],
            'box': [round(v, 1) for v in got['box']],
        })
        for m in members:
            # 成员的**小名**写在院子那一格里（小一号、次要色）—— 读者要看得出
            # "这里有个后院井台"，但它不是一栋独立的房子。
            # [EN] The member's **small name** goes inside its yard cell (smaller, secondary colour):
            # [EN] the reader should see "there is a well terrace here" without it becoming a building.
            mx, my = pos[m.name]
            shapes.append(MM._text(mx, my, _disp(m), size=8,
                                   color=pal.get('muted', '#8a9099'),
                                   font=font, center=True))

    for p in marks:
        cx, cy = pos[p.name]
        w = SIZE_W.get(str(getattr(p, 'size', '中')), 2)
        r = 2.6 + 1.1 * w
        here = bool(current) and p.name == current
        col = pal.get('here', '#b23028') if here else pal.get('ink', '#4a4f57')
        size = CITY_FONT.get(w, 11)
        disp = _disp(p)
        # ★★ 独立地物（桥/渡/山/树/市/门/亭/台）**永远画符号**，不画圆点：
        #   它们不是建筑，用圆点会让读者以为"这里有一栋房子"。
        # [EN] ★★ Standalone features (bridge / ferry / hill / trees / market / gate / pavilion /
        # [EN] terrace) **always get a symbol**, never a dot: they are not buildings, and a dot would
        # [EN] read as "there is a house here".
        kind = str(getattr(p, 'shape', '桥') or '桥')
        rr = 4.0 + 1.5 * w
        shapes.append(fcv.Circle(cx, cy, rr + 2.0, paint=ft.Paint(
            color=pal.get('on_paper', '#fffdf8'), style=ft.PaintingStyle.FILL)))
        _feature_symbol(shapes, kind, cx, cy, rr, pal, here=here)
        if (kind, GLYPH_LABEL.get(kind, '其他地物')) not in info['features']:
            info['features'].append((kind, GLYPH_LABEL.get(kind, '其他地物')))
        lw, lh = _est(disp, size)
        lx, ly = _place_label((cx - r, cy - r, cx + r, cy + r), lw, lh, labels, box)
        labels.append((lx, ly, lw, lh))
        shapes.append(MM._text(lx + lw / 2.0, ly, disp, size=size, color=col,
                               font=font, center=True, bold=here))
    return info


# ══════════════════════════════════════════════════════════════════════
#  城际图：政区面 + 城镇节点 + 官道 + 山河
# [EN] Region map: administrative areas + settlement nodes + highways + terrain
# ══════════════════════════════════════════════════════════════════════
def build_region_shapes(shapes: list, layout, places: list, px, *,
                        pal: dict, font: str | None = None,
                        span: tuple | None = None,
                        current: str = '',
                        style=None):
    """在 `shapes` 上画一张**城际图**（标准地图的元素，但只留骨架）。

    ## 只画五样（用户："元素更少"）

    1. **政区面**：Voronoi 分区，**极淡**填充 + **虚线**边界 —— 让人知道"这一片归这座城",
       但不抢戏；
    2. **水系面**：河湖加宽成带；
    3. **山地符号**：名字带「山/岭/峰」的地点，画**三角符号**（标准地图的山地记号），
       不画成城镇圆点 —— 山不是聚落；
    4. **官道**：`links` 按两端等级分级，**双线**（古驿道/官道的画法）；
    5. **城镇节点**：按 `settlement_rank` 分四级符号（都城/县城/镇/村），
       等级越高字越大 —— 这是城际图上**唯一**能传达"哪座城重要"的手段。

    ## 三种形态（`Style.城际`，2026-10-26 接上）

    这个字段一直写在档案里、从来没被读过，于是"山河为主的古代州府图"和"政区为主的
    近代/现代图"画得一模一样；舟船的世界更是被画出了一圈**根本不存在的国界**。

    * `terrain` 地形为主：政区面压到最淡（它是背景），山地符号放大、水系加宽；
    * `administrative` 政区为主：政区面与虚线界加重（现代/近代的读法就是"这一片属谁"），
      地形退一档；
    * `nautical` 航路图：**一条政区界都不画**，水面加深，航路画**虚线**，港口画**锚符号**。
      海图上没有国界，也没有"官道"。

    Returns:
        `{'nodes': [(name, x, y, rank)], 'roads': [(a, b, rank)], 'rivers': [...],
          'form': 'terrain'|'administrative'|'nautical', 'anchors': [...]}`
        —— 给判据用的**结构**（判据不该去猜图元，那是最脆的判法）。
        注意：函数**返回数据同时也画图**，两者是同一趟算出来的（不是两份）。

    ★ 不画街道、不画房屋：这是城际图，"一条街"在这个尺度上不存在。
      硬画会让读者以为"从这儿走两步就到"，而实际可能要走三天。

    [EN] Draw an **inter-city map** (standard map elements, skeleton only). Only five things:
    [EN] (1) administrative areas as very light Voronoi cells with **dashed** borders; (2) water
    [EN] bands; (3) **mountain symbols** (triangles) for places named 山/岭/峰 -- a mountain is not a
    [EN] settlement; (4) highways as graded double lines; (5) settlement nodes in four ranks by
    [EN] `settlement_rank`, with label size following rank -- the only way this scale can convey
    [EN] "which town matters". Returns the underlying structure for the criteria (guessing from
    [EN] drawing primitives is the most brittle kind of check), computed in the same pass as the
    [EN] drawing, never as a second copy. ★ No streets, no houses: at this scale "one street" does not
    [EN] exist, and drawing it would suggest "two steps away" when the truth may be three days.
    """
    form = region_form(style)
    info = {'nodes': [], 'roads': [], 'rivers': [], 'mountains': [], 'waters': [],
            'form': form, 'anchors': []}
    if not places:
        return info
    pos = {p.name: px(p) for p in places}
    box = span or _auto_span(pos)
    # 形态决定笔触（一处定义，下面各段都读它）
    # [EN] The form decides the strokes (defined once here; every block below reads it)
    _naut = (form == REGION_NAUTICAL)
    _terr = (form == REGION_TERRAIN)
    area_fill_k = 0.0 if _naut else (0.10 if _terr else 0.20)   # 越淡＝越是背景
    area_ink_k = 0.0 if _naut else (0.38 if _terr else 0.60)
    water_w = 18.0 if _naut else (14.0 if _terr else 12.0)
    mt_k = 1.25 if _terr else 0.9

    # ① 政区面（极淡 + 虚线边）；**航路图不画政区**
    # [EN] 1. Administrative areas (very light, dashed borders); **none on a nautical chart**
    if not _naut:
        seeds = [(p.name, pos[p.name][0], pos[p.name][1]) for p in places]
        cells = voronoi(seeds, box)
        area_fill = _mix(pal.get('paper', '#f8f4ea'), pal.get('link', '#c5bda9'), area_fill_k)
        area_line = _mix(pal.get('paper', '#f8f4ea'), pal.get('muted', '#8a9099'), area_ink_k)
        # ⚠ 相邻两个单元**共享同一条边**，各画一遍 ⇒ 虚线被画两次（实测 6 个单元切出
        #   524 个 `Line`）。用"顶点对（四舍五入到 0.1）"去重，同一条边只画一次：
        #   数量减半，而且重叠处不会因为两次描边变粗（视觉上更干净）。
        # [EN] Neighbouring cells **share an edge**, and each drew it => dashes drawn twice
        # [EN] (measured: 524 `Line`s from 6 cells). Dedupe by the vertex pair rounded to 0.1, so
        # [EN] each edge is drawn once: halves the count and stops doubled strokes looking thicker.
        _edge_seen: set = set()
        for nm, poly in cells.items():
            els = [fcv.Path.MoveTo(poly[0][0], poly[0][1])]
            els += [fcv.Path.LineTo(x, y) for x, y in poly[1:]]
            els.append(fcv.Path.Close())
            shapes.append(fcv.Path(els, paint=ft.Paint(color=area_fill,
                                                     style=ft.PaintingStyle.FILL)))
            # 虚线边界：标准地图的政区界就是虚线（实线会被读成"墙"）
            # [EN] Dashed borders: political boundaries are dashed on real maps (a solid line reads
            # [EN] as a wall).
            for k in range(len(poly)):
                a = poly[k]
                b = poly[(k + 1) % len(poly)]
                key = tuple(sorted([(round(a[0], 1), round(a[1], 1)),
                                    (round(b[0], 1), round(b[1], 1))]))
                if key in _edge_seen:
                    continue
                _edge_seen.add(key)
                _dashed(shapes, a, b, area_line)

    # ② 水系：**同一个 `draw_water()`**（城际图窄一点：`band` 小）
    # [EN] 2. Water: the **same `draw_water()`** (narrower on the region map via `band`)
    #
    # ★ 原来这里另写一份（"12~18px 两层"，航路图再加一层 2.6 倍的海底），与城市图各算一套。
    #   同一条河在两张图上画法不同，海岸线在一张上对、一张上错 —— 就是"两处实现必然漂"。
    #   现在只有 `band` 不同。
    # [EN] This used to be a second copy (12-18px, two layers, plus a 2.6x bed on charts) computed
    # [EN] separately from the city map, so one river was drawn two ways and the coastline was right on
    # [EN] one and wrong on the other -- the classic "two implementations always drift". Now only `band`
    # [EN] differs.
    _wt = draw_water(shapes, layout, px, pal, box, band=water_w, places=places)
    if _wt.get('kind'):
        # ⚠ **只记类型，不要动 `info['waters']`**：两个渲染器里这个键的语义不同 ——
        #   城市图是 `bool`（"这张图有水吗"），城际图是**列表**（水体符号的坐标）。
        #   第一版统一写成 `bool(...)`，城际图当场崩在 `info['waters'].append(...)`。
        # [EN] ⚠ **Only record the kind; do not touch `info['waters']`**: that key means different
        # [EN] things in the two renderers -- a `bool` in the city map ("does this map have water")
        # [EN] and a **list** of water-symbol positions in the region map. The first version wrote a
        # [EN] `bool(...)` to both and the region map crashed on `info['waters'].append(...)`.
        info['water_kind'] = _wt['kind']
        # ★ 渲染层**自己记**"画了多大一片水"：判据读它，不要从图元反推
        #   （城市图上街区、建筑都是填充面，靠"数填充面"分不出哪片是水 —— 实测 S1 误抓 61 个）。
        # [EN] The renderer **records** how much water area it drew; criteria read it instead of
        # [EN] inferring semantics from primitives (blocks and buildings are filled faces too, so
        # [EN] "count the filled faces" cannot tell which one is water -- S1 caught 61 false ones).
        info['water_poly'] = _wt.get('sea') or _wt.get('lake') or []
        info['coast_line'] = _wt.get('coast') or []
    if _wt.get('waters'):
        info['rivers'].append([tuple(round(v, 1) for v in px(_P(a, b)))
                               for a, b in (layout.water or [])])

    # ③ 官道（先把路画上，节点压在上面）
    # [EN] 3. Highways first, so nodes sit on top
    # ★★★ 2026-10-26：**改走与城市图同一份分级**（`scale.road_class`）。
    #   原来这里是 `2.0 + 1.6 * rank`，城市图是 `5.0 + 2.6 * 端点size` ——
    #   两份各算一套 ⇒ 同一条路在两张图上粗细比例不一致，而它们是**同一份 `links`**。
    #   现在两边都读 `scale.ROAD_SPEC`，比例天然一致。
    #   ⚠ 城际图故意画得**更细**一档（`REGION_ROAD_SCALE`）：这个尺度上一根线和
    #     一个城的圆点差不多粗就会互相干扰，标准地图在省域尺度也是细线。
    # [EN] ★★★ 2026-10-26: **same classification as the city map** (`scale.road_class`). This used
    # [EN] to be `2.0 + 1.6 * rank` while the city map used `5.0 + 2.6 * end size` -- two formulas,
    # [EN] so the same road had a different thickness ratio on the two maps even though they share one
    # [EN] `links`. Both now read `scale.ROAD_SPEC`, so the ratios match by construction. ⚠ The region
    # [EN] map is drawn **one notch thinner** (`REGION_ROAD_SCALE`): at this scale a line as thick as a
    # [EN] town dot interferes with it, and provincial-scale maps use thin lines for the same reason.
    for lk in (getattr(layout, 'links', None) or []):
        a, b = pos.get(lk.get('a')), pos.get(lk.get('b'))
        if not (a and b):
            continue
        ra = _rank_of_place(lk.get('a'), places, style)
        rb = _rank_of_place(lk.get('b'), places, style)
        cls = SC.road_class(ra, rb, top=SC.TOP_REGION)
        # 航路图：航线画**虚线**（实线会被读成陆上的官道或堤）
        # [EN] On a chart, routes are **dashed** (a solid line reads as a highway or a dyke)
        _road_seg(shapes, a, b, cls, pal, k=REGION_ROAD_SCALE, dashed=_naut)
        info['roads'].append((str(lk.get('a')), str(lk.get('b')), cls))

    # ④ 山地符号 + ⑤ 城镇节点
    # [EN] 4. Mountain symbols + 5. settlement nodes
    labels: list = []
    for p in places:
        cx, cy = pos[p.name]
        if _is_mountain(p.name):
            _mountain(shapes, cx, cy, pal, k=mt_k)
            info['mountains'].append((p.name, cx, cy))
            size = 11
            col = pal.get('muted', '#8a9099')
            bold = False
        elif _is_water(p.name):
            # ★ 2026-10-26 实测：`黑水河` 原来按 `settlement_rank` 判成了**村庄**（rank 1），
            #   于是图上那个"一条河"被画成一个村子的小圆点。河不是聚落，要有自己的符号。
            # [EN] Measured 2026-10-26: `黑水河` fell through to `settlement_rank` = 1 (a village),
            # [EN] so a river was drawn as a tiny village dot. A river is not a settlement.
            _water_symbol(shapes, cx, cy, pal)
            info['waters'].append((p.name, cx, cy))
            size = 11
            col = pal.get('water_deep', pal.get('water', '#8fb0c4'))
            bold = False
        else:
            rank = settlement_rank(p.name, size=str(getattr(p, 'size', '') or ''),
                                   style=style)
            # 航路图上，港口用**锚符号**（海图的约定记号），不用城镇圆点
            # [EN] On a chart, ports get an **anchor** (the chart convention), not a town dot
            if _naut and _is_port(p.name, style):
                _anchor_symbol(shapes, cx, cy, rank, pal,
                              here=(bool(current) and p.name == current))
                info['anchors'].append((p.name, cx, cy, rank))
            else:
                _town_symbol(shapes, cx, cy, rank, pal,
                             here=(bool(current) and p.name == current))
            info['nodes'].append((p.name, cx, cy, rank))
            size = RANK_FONT.get(rank, 10)
            col = (pal.get('here', '#b23028') if (current and p.name == current)
                   else pal.get('ink', '#4a4f57'))
            bold = rank >= 3
        disp = _disp(p)
        lw, lh = _est(disp, size)
        rect = (cx - 8, cy - 8, cx + 8, cy + 8)
        lx, ly = _place_label(rect, lw, lh, labels, box)
        labels.append((lx, ly, lw, lh))
        shapes.append(MM._text(lx + lw / 2.0, ly, disp, size=size, color=col,
                               font=font, center=True, bold=bold))
    return info


# ══════════════════════════════════════════════════════════════════════
#  甲板图：船体 + 舱段（第四种尺度，2026-10-26）
# [EN] Deck plan: hull + compartments (the fourth scale, 2026-10-26)
# ══════════════════════════════════════════════════════════════════════
def _hull_halfw(t: float) -> float:
    """船体在纵向位置 `t`（0=船尾, 1=船首）的**半宽比例**（0~1）。

    ★ 一条真船的平面轮廓：中段等宽（平行中体）、首端收成尖、尾端留一块方尾。
      这里只用三个参数把它写出来，**不追求真实线型** —— 我们没有这条船的数据，
      画得太像才是编。读者只要看出"这是船不是房子"。
    [EN] Half-width ratio of the hull at longitudinal position `t` (0 = stern, 1 = bow). ★ A real
    [EN] hull is parallel in the midbody, pointed at the bow and squared at the transom; three
    [EN] parameters express that. **We do not chase real lines**: we have no data for this ship and
    [EN] looking too exact would be fabrication. The reader only needs "a ship, not a house".
    """
    t = max(0.0, min(1.0, float(t)))
    if t < 0.18:                       # 方尾
        return 0.62 + 0.38 * (t / 0.18)
    if t > 0.72:                       # 首部收尖
        return max(0.0, 1.0 - ((t - 0.72) / 0.28) ** 1.35)
    return 1.0


def _hull_poly(box: tuple, *, steps: int = 26) -> list[tuple[float, float]]:
    """船体轮廓（闭合多边形）：上缘从尾到首、下缘再回来。

    [EN] The hull outline as a closed polygon: along the upper edge stern to bow, then back.
    """
    x0, y0, x1, y1 = (float(v) for v in box)
    cy = (y0 + y1) / 2.0
    hw = (y1 - y0) / 2.0
    pts: list[tuple[float, float]] = []
    for k in range(steps + 1):
        t = k / steps
        x = x0 + (x1 - x0) * t
        pts.append((x, cy - hw * _hull_halfw(t)))
    for k in range(steps, -1, -1):
        t = k / steps
        x = x0 + (x1 - x0) * t
        pts.append((x, cy + hw * _hull_halfw(t)))
    return pts


def _clip_x(poly: list[tuple[float, float]], bx: float, *, left: bool = True):
    """把多边形裁到竖线 `x = bx` 的左侧（或右侧）。

    ★ 复用 `_clip_half`：取 `s=(bx-1,0)`、`o=(bx+1,0)`，那条"垂直平分线"正好是 `x=bx`。
      不另写一套裁剪 —— 两处实现必然漂（本项目头号老坑）。
    [EN] Clip a polygon to the left (or right) of the vertical line `x = bx`. ★ Reuses
    [EN] `_clip_half`: with s=(bx-1,0) and o=(bx+1,0) its "bisector" is exactly `x=bx`. Do not write
    [EN] a second clipper -- two implementations always drift.
    """
    if left:
        return _clip_half(poly, bx - 1.0, 0.0, bx + 1.0, 0.0)
    return _clip_half(poly, bx + 1.0, 0.0, bx - 1.0, 0.0)


def _path_of(poly: list[tuple[float, float]]) -> list:
    """多边形 → flet 路径元素（首点 MoveTo，其余 LineTo，最后 Close）。"""
    els = [fcv.Path.MoveTo(poly[0][0], poly[0][1])]
    els += [fcv.Path.LineTo(x, y) for x, y in poly[1:]]
    els.append(fcv.Path.Close())
    return els


def build_deck_shapes(shapes: list, layout, places: list, px, *,
                      pal: dict, font: str | None = None,
                      span: tuple | None = None,
                      current: str = '',
                      style=None) -> dict:
    """画一张**甲板图**：船体轮廓 + 沿龙骨切的舱段 + 舱壁与舱门。

    ## 为什么舟船不能走室内平面（用户第 11 轮之后自查发现的真错）

    `roomplan` 解的是"矩形外轮廓里分带切房间、拼满、共用墙开门"。船的平面是
    **狭长的一根**、纵向沿龙骨分舱、横向分舷、甲板是唯一的见天面、底舱无窗。
    用同一套解算器，得到的是一艘"四合院形状的船"：房间围着中庭、楼梯在正中。

    ## 画法（与室内平面共享纪律，不共享解算器）

    1. **船体**：一条纵向轮廓（平行中体 + 尖首 + 方尾），双线画成"舷侧"；
    2. **分舱**：按**地点自己的 x 次序**把船体切段，段宽按面积权重（`SIZE_W`）分配 ——
       与室内图同一个"谁大谁占得多"的相对原则，但切法是一维的（沿龙骨）；
       ★ 舱段多边形 = 船体轮廓被两条竖线裁出来的那一块 ⇒ 首尾的舱段自然跟着收尖，
         不会出现"方盒子戳出船头"；
    3. **舱壁与舱门**：相邻舱段之间的竖壁加厚成双线，中段留缺口 + 一道门扇
       （与室内平面同一个门的画法）—— 船上是"水密门/舱门"，画法一致、说法不同；
    4. **分甲板**：楼上/甲板层（`roomplan.floor_of` 判定）单独画一条船体，纵向叠放，
       每层带自己的标签（"甲板"/"B1"…）。这是船图分页的常规做法。

    Returns:
        `{'decks': [{'floor': n, 'label': str,
                     'compartments': [(名字, x左, x右)]}], 'form': 'deck'}`

    ★ 不画的东西：航向、吃水、龙骨剖面 —— 我们没有船型数据，画了就是编。
    [EN] Draw a **deck plan**: hull outline + compartments cut along the keel + bulkheads and doors.
    [EN] ## Why a ship cannot use the indoor solver: `roomplan` solves "cut rooms inside a
    [EN] rectangular outline"; a hull is one long narrow body divided along the keel, the deck is the
    [EN] only open-to-sky surface and the hold has no windows. The same solver yields a ship shaped
    [EN] like a courtyard house. ## Drawing (same discipline as the indoor plan, different solver):
    [EN] (1) hull = one longitudinal outline (parallel midbody, pointed bow, square transom) drawn as
    [EN] a double line; (2) compartments = the hull cut by verticals at the places' own x order, widths
    [EN] proportional to `SIZE_W` -- the same "bigger gets more" principle, but cut in one dimension,
    [EN] and because each compartment polygon is the hull clipped by two verticals, bow compartments
    [EN] follow the taper instead of poking out as boxes; (3) bulkheads thickened with a gap plus a
    [EN] door leaf (the same door drawing as the indoor plan -- on board it is a watertight door, but
    [EN] the drawing is identical); (4) each upper deck (`roomplan.floor_of`) drawn as its own hull,
    [EN] stacked, with its own label -- the usual convention for ship plan sheets. Returns the
    [EN] structure for the criteria. ★ Not drawn: heading, draught, keel section -- we have no hull
    [EN] data and drawing them would be fabrication.
    """
    info: dict = {'decks': [], 'form': 'deck'}
    if not places:
        return info
    from image_gen import roomplan as RP            # 局部 import：避免模块级循环依赖
    pos = {p.name: px(p) for p in places}
    box = span or _auto_span(pos)

    # 按层分组（甲板/上层甲板 vs 舱室 vs 底舱）；判不出层的都算第一层
    # [EN] Group by deck (upper deck / cabins / hold); anything unreadable counts as deck 1
    # ⚠ 用**原样的层号**分组，包括负数（底舱＝B1）：把它夹成 1 会让底舱与主甲板上的舱室
    #   合并到同一张图里 —— 那是"两个隔着一层甲板的地方挨在一起"。
    # [EN] Group by the **raw** floor number, negatives included (hold = B1): clamping it to 1
    # [EN] merges the hold into the main-deck plan -- i.e. "two places one deck apart, side by side".
    groups: dict[int, list] = {}
    for p in places:
        try:
            fl = int(RP.floor_of(str(p.name), style)) if style is not None else 1
        except Exception:                                     # noqa: BLE001
            fl = 1
        groups.setdefault(fl, []).append(p)
    floors = sorted(groups)
    if len(floors) > 3:                                       # 三层以上挤不下：只画最上面的三层
        floors = floors[-3:]

    # 每层一条船体，纵向叠放
    # [EN] One hull per deck, stacked vertically
    x0, y0, x1, y1 = (float(v) for v in box)
    n = len(floors)
    band_h = (y1 - y0) / n
    for i, fl in enumerate(floors):
        by0 = y0 + band_h * i
        by1 = by0 + band_h
        pad = min(14.0, band_h * 0.10)
        hull_box = (x0 + 6.0, by0 + pad, x1 - 6.0, by1 - pad - 13.0)
        if hull_box[3] - hull_box[1] < 26.0:
            hull_box = (hull_box[0], hull_box[1], hull_box[2], hull_box[1] + 26.0)
        hull = _hull_poly(hull_box)

        # 船体：先填、再双线描（舷侧）
        # [EN] Hull: fill first, then a double stroke for the sides
        shapes.append(fcv.Path(_path_of(hull), paint=ft.Paint(
            color=_mix(pal.get('paper', '#f8f4ea'), pal.get('wall', '#b9b1a0'), 0.08),
            style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Path(_path_of(hull), paint=ft.Paint(
            color=pal.get('ink', '#4a4f57'), stroke_width=4.6,
            stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
        shapes.append(fcv.Path(_path_of(hull), paint=ft.Paint(
            color=pal.get('paper', '#f8f4ea'), stroke_width=2.4,
            stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))

        # 分舱：按地点自己的 x 排序，段宽按面积权重
        # [EN] Compartments: ordered by the places' own x, widths by area weight
        ps = sorted(groups[fl], key=lambda q: (float(pos[q.name][0]), str(q.name)))
        ws = [_sizew(q.name, places) for q in ps]
        tot = float(sum(ws)) or 1.0
        xl = hull_box[0] + (hull_box[2] - hull_box[0]) * 0.10
        xr = hull_box[2] - (hull_box[2] - hull_box[0]) * 0.16
        cuts = [xl]
        acc = 0.0
        for w in ws[:-1]:
            acc += float(w)
            cuts.append(xl + (xr - xl) * (acc / tot))
        cuts.append(xr)
        cy = (hull_box[1] + hull_box[3]) / 2.0
        comps: list = []
        for k, q in enumerate(ps):
            xa, xb = cuts[k], cuts[k + 1]
            piece = _clip_x(_clip_x(hull, xa, left=False), xb, left=True)
            if len(piece) < 3:
                piece = [(xa, hull_box[1]), (xb, hull_box[1]),
                         (xb, hull_box[3]), (xa, hull_box[3])]
            comps.append((q.name, xa, xb))
            # 舱段填充（浅）＋ 舱壁竖线（下面单独画，免得同一条壁两次描成双粗）
            # [EN] Compartment fill (light); bulkheads drawn separately below so one wall is not
            # [EN] stroked twice and read as extra thick
            shapes.append(fcv.Path(_path_of(piece), paint=ft.Paint(
                color=_mix(pal.get('paper', '#f8f4ea'), pal.get('ink', '#4a4f57'), 0.03),
                style=ft.PaintingStyle.FILL)))
        info['decks'].append({'floor': fl, 'label': SC.floor_label(fl),
                              'compartments': comps})

        # 舱壁：相邻舱段之间的竖壁（双线 + 中段舱门缺口 + 门扇）
        # [EN] Bulkheads between adjacent compartments (double line, a doorway gap, a door leaf)
        for k in range(1, len(cuts) - 1):
            bx = cuts[k]
            shapes.append(fcv.Line(bx, hull_box[1], bx, cy - 9.0,
                                  paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                                 stroke_width=3.0)))
            shapes.append(fcv.Line(bx, cy + 9.0, bx, hull_box[3],
                                  paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                                 stroke_width=3.0)))
            # 门扇：从缺口下沿斜开 45°（与室内平面同一个记号）
            # [EN] Door leaf: swung 45 degrees from the lower edge of the gap (same mark as indoors)
            shapes.append(fcv.Line(bx, cy + 9.0, bx + 9.0, cy,
                                  paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                                 stroke_width=1.2,
                                                 stroke_cap=ft.StrokeCap.ROUND)))

        # 舱名
        # [EN] Compartment names
        for k, q in enumerate(ps):
            here = bool(current) and q.name == current
            size = 10 if _sizew(q.name, places) <= 2 else 11
            mx = (cuts[k] + cuts[k + 1]) / 2.0
            shapes.append(MM._text(mx, cy - size * 0.5, _disp(q), size=size,
                                   color=(pal.get('here', '#b23028') if here
                                          else pal.get('ink', '#4a4f57')),
                                   font=font, center=True, bold=here))
        # 层标签（船体下方）
        # [EN] Deck label (below the hull)
        shapes.append(MM._text(x0 + 18.0, hull_box[3] + 2.0,
                               f"{SC.LABEL[SC.DECK]} · {SC.floor_label(fl)}",
                               size=9, color=pal.get('muted', '#8a9099'),
                               font=font, center=True))
    return info

# ══════════════════════════════════════════════════════════════════════
#  小零件
# [EN] Small parts
# ══════════════════════════════════════════════════════════════════════
class _P:
    """把 `(x, y)` 包成一个只有坐标的假 `Place`，好复用 `px()`。

    ★ 为什么不直接乘：`px` 是"地点 → 像素"的**唯一**换算（含内边距、缩放、翻边）。
      在这里手写一遍乘法，就又多了一套口径 —— 本项目《两处实现必然漂》的老坑。
    [EN] Wraps `(x, y)` in a coordinates-only stand-in so `px()` can be reused. ★ Why not multiply
    [EN] directly: `px` is the **single** place->pixel conversion (padding, scale, flips). Doing the
    [EN] maths here again creates a second definition -- this project's classic drift pit.
    """

    __slots__ = ('x', 'y', 'name', 'size', 'shape', 'short', 'note', 'room')

    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.name = ''
        self.size = '中'
        self.shape = '屋'
        self.short = ''
        self.note = ''
        self.room = ''


def _auto_span(pos: dict) -> tuple:
    """没给 `span` 时的包围盒（外扩一点，别让边缘的点贴框）。
        English: Bounding box when `span` is not given (padded so edge places do not touch the frame).
    """
    xs = [v[0] for v in pos.values()] or [0.0, 100.0]
    ys = [v[1] for v in pos.values()] or [0.0, 100.0]
    return (min(xs) - 30, min(ys) - 30, max(xs) + 30, max(ys) + 30)


def _sizew(name, places) -> int:
    for p in places:
        if p.name == name:
            return SIZE_W.get(str(getattr(p, 'size', '中')), 2)
    return 1


def _disp(p) -> str:
    """图上显示的名字：有简称用简称，否则原名（超过 7 字截断）。
        English: Label text: the short name when present, else the name (truncated past 7 chars).
    """
    s = str(getattr(p, 'short', '') or '').strip()
    if s:
        return s
    n = str(getattr(p, 'name', '') or '')
    return n if len(n) <= 7 else n[:7]


def _est(text: str, size: int) -> tuple:
    """估文字块大小（宽, 高）。中文按 `size` 宽，西文按 0.55×。
        English: Estimate a text block's size; CJK counts `size` per char, Latin about 0.55.
    """
    w = 0.0
    for ch in str(text or ''):
        w += float(size) if '\u4e00' <= ch <= '\u9fff' else float(size) * 0.55
    return (max(8.0, w), float(size) + 3.0)


def _place_label(rect, lw, lh, taken, bounds) -> tuple:
    """在 `rect` 外侧挑一个**不与已有标签重叠**的位置（8 个候选位，取第一个不重叠的）。

    ★ 与 `label_place.place_label` 同一个思路，但这里**不 import 那个模块** ——
      它依赖 `map_layout` 的一堆东西，而 `scalemap` 只要一个纯几何函数。
      两边纪律一致：**先试 8 个方位，全重叠时取重叠最小的那个**（绝不叠着写）。
    [EN] Pick a position **outside** `rect` that overlaps no existing label (8 candidates, first
    [EN] non-overlapping). ★ Same idea as `label_place.place_label`, but this module does not import
    [EN] it -- that one drags in half of `map_layout` while all we need is pure geometry. Both follow
    [EN] the same discipline: try 8 positions, and when all overlap take the least-overlapping one
    [EN] (never write on top of another label).
    """
    x0, y0, x1, y1 = rect
    gap = 3.0
    cands = [
        (x0, y1 + gap), (x1 - lw, y1 + gap),                 # 下
        (x0, y0 - lh - gap), (x1 - lw, y0 - lh - gap),       # 上
        (x1 + gap, (y0 + y1) / 2 - lh / 2),                  # 右
        (x0 - lw - gap, (y0 + y1) / 2 - lh / 2),             # 左
        (x1 - lw / 2, y1 + gap + lh),                        # 更下
        (x1 - lw / 2, y0 - 2 * lh - gap),                    # 更上
    ]
    bx0, by0, bx1, by1 = bounds
    best, best_ov = None, None
    for (lx, ly) in cands:
        # 夹进绘图区（超出画框就等于没写）
        lx = min(max(lx, bx0 + 1), bx1 - lw - 1)
        ly = min(max(ly, by0 + 1), by1 - lh - 1)
        ov = 0.0
        for (tx, ty, tw, th) in taken:
            ox = min(lx + lw, tx + tw) - max(lx, tx)
            oy = min(ly + lh, ty + th) - max(ly, ty)
            if ox > 0 and oy > 0:
                ov += ox * oy
        if ov <= 0.0:
            return (lx, ly)
        if best_ov is None or ov < best_ov:
            best, best_ov = (lx, ly), ov
    return best or (x0, y1 + gap)


def _mountain(shapes: list, x: float, y: float, pal: dict, *, k: float = 1.0) -> None:
    """山地符号：**一个三角 + 内画一道折线**（标准地图的等高线示意，不是真等高线）。

    ★ 说清它是示意：我们没有高程数据，画"真等高线"就是编。三角形是**约定符号**，
      读者不会以为它表示 1200 米。
    ★ `k` 是尺度倍数：地形为主的城际图（`terrain`）把山放大一档 —— 那种图上
      山是**主体**；政区为主的图上它是背景，不能和城镇节点抢。
    [EN] Mountain symbol: a triangle with one inner zigzag (a schematic, not real contours). ★ Say
    [EN] it is schematic: we have no elevation data, so real contours would be invention. A triangle
    [EN] is a **conventional symbol** and no reader takes it for "1200 m". ★ `k` scales it: on a
    [EN] terrain-led map hills are the **subject**; on an administrative one they are background and
    [EN] must not compete with settlement nodes.
    """
    r = 9.0 * max(0.5, float(k or 1.0))
    p1 = (x, y - r)
    p2 = (x + r * 0.95, y + r * 0.7)
    p3 = (x - r * 0.95, y + r * 0.7)
    els = [fcv.Path.MoveTo(*p1), fcv.Path.LineTo(*p2), fcv.Path.LineTo(*p3),
           fcv.Path.Close()]
    shapes.append(fcv.Path(els, paint=ft.Paint(
        color=_mix(pal.get('paper', '#f8f4ea'), pal.get('muted', '#8a9099'), 0.5),
        style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Path(els, paint=ft.Paint(
        color=pal.get('ink', '#4a4f57'), stroke_width=1.2,
        style=ft.PaintingStyle.STROKE)))
    shapes.append(fcv.Line(x - r * 0.42, y + r * 0.2, x - r * 0.10, y - r * 0.25,
                          paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                         stroke_width=1.0)))
    shapes.append(fcv.Line(x - r * 0.10, y - r * 0.25, x + r * 0.28, y + r * 0.25,
                          paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                         stroke_width=1.0)))


def _town_symbol(shapes: list, x: float, y: float, rank: int, pal: dict,
                 *, here: bool = False) -> None:
    """城镇节点：**等级越高圈越大**；都城在圈外再套一圈（标准地图的"首都"记号）。

    ★ 为什么按等级改大小、而不是按 `size`：城际图上"这座城是我这轮去过的那间茶棚"
      和"这座城是三万人的州府"是两件事 —— 后者才是读者要的信息。
    [EN] Settlement node: bigger ring for higher rank; a capital gets a second outer ring (the
    [EN] standard "capital" mark). ★ Why rank rather than `size`: at this scale "the tea stall I
    [EN] visited" and "the prefectural city of thirty thousand" are different facts -- the latter is
    [EN] what the reader needs.
    """
    r = RANK_R.get(rank, 3.0)
    col = pal.get('here', '#b23028') if here else pal.get('ink', '#4a4f57')
    paper = pal.get('on_paper', '#fffdf8')
    # 白边先画：压在路与政区界上面，符号才"浮"得起来（标准地图的 halos 做法）
    # [EN] Draw the white halo first so the symbol sits above roads and boundaries (the standard
    # [EN] "halo" technique on real maps).
    shapes.append(fcv.Circle(x, y, r + 1.2, paint=ft.Paint(
        color=paper, style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Circle(x, y, r, paint=ft.Paint(
        color=col, style=ft.PaintingStyle.FILL)))
    if rank >= 4:
        # 都城：外面再套一圈（空心环）
        # [EN] Capital: an extra hollow ring outside
        shapes.append(fcv.Circle(x, y, r + 3.4, paint=ft.Paint(
            color=col, stroke_width=1.1, style=ft.PaintingStyle.STROKE)))
    elif rank == 3:
        # 县城：实心圆里挖一个白心（"有中心"的记号）
        # [EN] County seat: a hollow white centre inside the filled dot
        shapes.append(fcv.Circle(x, y, r * 0.42, paint=ft.Paint(
            color=paper, style=ft.PaintingStyle.FILL)))


def _rank_of_place(name, places, style=None) -> int:
    """按地点名（连同作者给的 `size`）判等级。**名字取不到 size 也照样判**。

    ★ 为什么要从 `places` 里找 size：等级的两级判据（名字→建制词、其次→作者的
      `size`）必须在**一处**取值，否则"画符号用的等级"和"定路宽用的等级"会不同 ——
      同一条路两端判成不同级，粗细就自相矛盾。
    [EN] Rank by name plus the author's `size`. ★ Why look `size` up in `places`: both tiers of
    [EN] the judgement must read from **one** place, or the rank used for the symbol and the rank
    [EN] used for the road width diverge -- the two ends of one road would disagree.
    """
    nm = str(name or '')
    size = ''
    for p in (places or []):
        if str(getattr(p, 'name', '') or '') == nm:
            size = str(getattr(p, 'size', '') or '')
            break
    return settlement_rank(nm, size=size, style=style)


#: 港口/锚地的名字特征（航路图上要画锚符号而不是城镇圆点）
# [EN] Name features of a port or anchorage (drawn as an anchor, not a town dot, on a chart)
PORT_WORDS = ('港', '码头', '锚地', '泊地', '渡口', '津渡',
              'port', 'harbor', 'harbour', 'anchorage', 'wharf', 'dock', 'bay')


def _is_port(name: str, style=None) -> bool:
    """这是不是一个港口/锚地（航路图上用锚符号）。

    ★ 与 `_rank_of_place` 分开：等级回答"多大"，这里回答"是不是港"。
      在建制词表里「港」常常是 2 级（镇/驿/渡），但**符号**该是锚不是圆点 ——
      符号表达"能不能停船"，等级表达"有多大"，两件事。
    [EN] Whether this is a port or anchorage (anchor symbol on a chart). ★ Separate from rank:
    [EN] rank answers "how big", this answers "can you moor here". The symbol says "you can moor",
    [EN] the rank says "how important" -- two different facts.
    """
    n = str(name or '')
    if not n:
        return False
    if any(w and w in n.lower() for w in PORT_WORDS):
        return True
    try:
        return bool(style is not None and style.rank_of(n) >= 2
                    and any(w and w in n for w in ('港', '湾', '滩')))
    except Exception:                                         # noqa: BLE001
        return False


def _anchor_symbol(shapes: list, x: float, y: float, rank: int, pal: dict,
                   *, here: bool = False) -> None:
    """**锚符号**（海图的港口记号）：竖杆 + 上横 + 底部圆弧 + 顶部环。

    ★ 为什么不全用城镇圆点：航路图上"这里能停船"是**唯一**有用的信息，
      一个实心圆点表达不了；而锚是海图的通用约定，不解释也认得。
    ★ 大小仍按等级（大港的锚大一号），但**形状不随等级变** —— 海图上港口就是港口。
    [EN] The **anchor** symbol (the chart convention for a port): shank, stock, crown arc, ring.
    ★ Why not reuse the town dot: on a chart "you can moor here" is the only useful fact and a
    [EN] filled dot cannot express it, while an anchor is understood without a legend. ★ Size still
    [EN] follows rank (a major port gets a bigger anchor) but the **shape never changes** -- on a
    [EN] chart a port is a port.
    """
    s = 0.78 + 0.12 * max(1, min(4, int(rank or 1)))
    col = pal.get('here', '#b23028') if here else pal.get('ink', '#4a4f57')
    paper = pal.get('on_paper', '#fffdf8')
    w = 1.7
    # 白色 halo：压在航线与水面上要浮得起来（与城镇节点同一套做法）
    # [EN] White halo so it sits above routes and water (same technique as the town nodes)
    shapes.append(fcv.Circle(x, y, 8.0 * s, paint=ft.Paint(
        color=paper, style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Line(x, y - 6.0 * s, x, y + 6.0 * s,
                          paint=ft.Paint(color=col, stroke_width=w,
                                         stroke_cap=ft.StrokeCap.ROUND)))
    shapes.append(fcv.Line(x - 4.0 * s, y - 3.2 * s, x + 4.0 * s, y - 3.2 * s,
                          paint=ft.Paint(color=col, stroke_width=w,
                                         stroke_cap=ft.StrokeCap.ROUND)))
    shapes.append(fcv.Circle(x, y - 6.2 * s, 1.6 * s, paint=ft.Paint(
        color=col, stroke_width=w, style=ft.PaintingStyle.STROKE)))
    # 锚爪：两段斜线接一段底弧（用两段折线近似，避免依赖 arc 的端点计算）
    # [EN] The crown: two slanted lines plus a shallow bottom (approximated with polylines rather
    # [EN] than arcs, to avoid depending on arc endpoint maths)
    shapes.append(fcv.Line(x - 5.2 * s, y + 2.6 * s, x - 2.6 * s, y + 5.4 * s,
                          paint=ft.Paint(color=col, stroke_width=w,
                                         stroke_cap=ft.StrokeCap.ROUND)))
    shapes.append(fcv.Line(x + 5.2 * s, y + 2.6 * s, x + 2.6 * s, y + 5.4 * s,
                          paint=ft.Paint(color=col, stroke_width=w,
                                         stroke_cap=ft.StrokeCap.ROUND)))
    shapes.append(fcv.Line(x - 2.6 * s, y + 5.4 * s, x + 2.6 * s, y + 5.4 * s,
                          paint=ft.Paint(color=col, stroke_width=w,
                                         stroke_cap=ft.StrokeCap.ROUND)))


def _dashed(shapes: list, a, b, color: str, *, dash: float = 8.0,
            gap: float = 6.0, width: float = 1.0) -> None:
    """在 `a`→`b` 上画虚线（政区界 / 航线的画法）。
        English: Dashed segment from `a` to `b` (how political boundaries and sea routes are drawn).
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L <= 0.5:
        return
    ux, uy = dx / L, dy / L
    t = 0.0
    while t < L:
        t2 = min(t + dash, L)
        shapes.append(fcv.Line(a[0] + ux * t, a[1] + uy * t,
                              a[0] + ux * t2, a[1] + uy * t2,
                              paint=ft.Paint(color=color, stroke_width=width)))
        t = t2 + gap


def _mix(c1: str, c2: str, t: float) -> str:
    """两个 `#rrggbb` 之间线性插值（`t=0` 得 c1）。**三色通道分别插**，别转 HSL。

    ★ 为什么不转 HSL：中式的纸色与墨色都在低饱和区，转 HSL 插值会让中间色**跳色**
      （纸黄变灰绿那种）。直接插 RGB 平实、可预期。
    [EN] Linear interpolation between two `#rrggbb` colours (t=0 gives c1), channel by channel.
    ★ Why not HSL: paper and ink sit at low saturation, and HSL interpolation makes the midpoint
    [EN] jump hue (paper yellow turning grey-green). Straight RGB is plain and predictable.
    """
    def rgb(s):
        s = str(s or '').lstrip('#')
        if len(s) == 3:
            s = ''.join(ch * 2 for ch in s)
        try:
            return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        except (ValueError, IndexError):
            return 128, 128, 128

    r1, g1, b1 = rgb(c1)
    r2, g2, b2 = rgb(c2)
    t = max(0.0, min(1.0, float(t)))
    return '#%02x%02x%02x' % (int(r1 + (r2 - r1) * t),
                              int(g1 + (g2 - g1) * t),
                              int(b1 + (b2 - b1) * t))


def _is_mountain(name: str) -> bool:
    """这是不是**山地**（城际图上要画三角符号，不画城镇圆点）。

    ⚠ 只认非常明确的：`山/岭/峰/丘/崖`。不认 `原/林/湖` —— 那是别的符号（平原/林地/水面），
      混进来会把"黑松林"画成一座山。
    [EN] Is this a **mountain** (triangle symbol on the region map, not a settlement dot)? Only
    [EN] clearly-mountain words: 山/岭/峰/丘/崖. Not 原/林/湖 -- those are other symbols, and mixing
    [EN] them in would draw "Black Pine Forest" as a mountain.
    """
    n = str(name or '')
    return any(k in n for k in ('山', '岭', '峰', '丘', '崖')) and \
        not any(k in n for k in ('山庄', '山房', '山门'))


def _is_green(name: str) -> bool:
    """这是不是**绿地**（公园/花园/林地/草坪/广场），城市图上要画绿面而不是圆点。

    ★ 只认名字里**明说**的：不按"看着像"猜。
    ⚠ 排除几个会误命的：`御花园` 在【室内/院落】尺度上是院子的一部分（那由室内图管），
      这里只服务城市尺度；`菜园/药圃/茶园` 是**生产用地**不是公共绿地，
      画成公园会让读者以为那儿可以去散步。所以它们不算。
    [EN] Is this **green space** (park/garden/grove/lawn/plaza) -- drawn as a green area rather than
    [EN] a dot on the city map. ★ Only what the name **states**; never "looks green". ⚠ Excluded:
    [EN] `御花园` belongs to a courtyard at the interior scale (handled by the indoor plan), and
    [EN] `菜园/药圃/茶园` are **productive land**, not public green -- drawing them as parks suggests
    [EN] the reader could stroll there.
    """
    n = str(name or '')
    if any(k in n for k in ('菜园', '药圃', '茶园', '苗圃', '田')):
        return False
    return any(k in n for k in ('公园', '花园', '林地', '树林', '草坪', '广场',
                               '绿地', '园苑', '苑'))


# ══════════════════════════════════════════════════════════════════════
#  水系：河 / 湖 / 海（**三种画法完全不同**）
# [EN] Water: river / lake / coast (three completely different drawings)
# ══════════════════════════════════════════════════════════════════════
#
# ★★★ 2026-10-27（用户）：「如果是海边等位置 看下是否可以正常绘制海岸线」。
#
#   查下来是**画不对**，而且原因不在美术，在数据结构：「`water` 是一条折线」这句话
#   能表达的东西**不止一种**，而三种东西的画法毫无共同点：
#
#     | 类型 | 折线的意思 | 正确画法 |
#     |------|-----------|----------|
#     | 河   | 河道中线 | 一条带（线居中加粗），两岸夹水 |
#     | 湖   | 闭合岸线 | 闭合轮廓 + 内部填充 |
#     | 海   | **陆与海的分界** | 一侧整片填充 + 一条实线海岸线 |
#
#   老实现一律"线居中加粗 22px"（`build_city_shapes`）／"12~18px"（`build_region_shapes`）。
#   对河正确；对海则是**两处都错**：
#     · 加粗是**居中**的 ⇒ 海被往陆地推了半个带宽（18px 带宽就是推 9px）；
#     · 海的那一面**完全没有填充** ⇒ 读者看到的是"沿着海岸有一条蓝色的河"，
#       而不是"这边是海、那边是陆"。
#
#   制图上的依据（GB/T 20257.1 海部要素 / 海图图式）：陆地与海的分界是**实线海岸线**，
#   海部以浅蓝平涂（浅海）表示；**等深线**是虚线 —— 我们没有水深数据，所以**不画等深线**
#   （画了就是编）。同理不画沙滩、礁石：没有材料。
#
#   ⇒ 判类型靠"从数据推"，不在提示词里碰运气。推断有明确纪律：
#     **判不准就当河**。因为把河画成海会平白填蓝半张图，比把海画成河更错。
#     上游若明确声明（`Layout.water_kind` / JSON 的 `水系类型`），一律以它为准。

#: 水系三态（**闭集**）
# [EN] The three water kinds (a closed set)
WK_RIVER = 'river'
WK_COAST = 'coast'
WK_LAKE = 'lake'
WK_ALL = (WK_RIVER, WK_COAST, WK_LAKE)

#: 图例用词（只此一份：判据与三个渲染器都读它）
# [EN] Legend wording (one copy; the criteria and all three renderers read it)
#: 图例用词（**图例直接用它**，不要在 floorplan 里另写一套说辞 —— 那样改一处会漏一处）
# [EN] Legend wording; the legend uses it directly (never write a second set in floorplan, or one
# [EN] side gets missed when the rule changes)
WK_LABEL = {WK_RIVER: '河流（带）', WK_COAST: '海域（实线海岸线）', WK_LAKE: '湖（闭合水面）'}

#: 上游可能写的中文/别名 → 三态。**只认这些**，其余当"没声明"。
# [EN] Chinese/alias spellings the caller may use; anything else counts as "not declared".
_WK_ALIAS = {
    'river': WK_RIVER, '河': WK_RIVER, '河流': WK_RIVER, '江': WK_RIVER, '河道': WK_RIVER,
    'lake': WK_LAKE, '湖': WK_LAKE, '湖泊': WK_LAKE, '潭': WK_LAKE,
    'coast': WK_COAST, 'seaside': WK_COAST, 'sea': WK_COAST,
    '海': WK_COAST, '海岸': WK_COAST, '海岸线': WK_COAST, '海域': WK_COAST, '海边': WK_COAST,
}

#: 判海岸线时，"一侧几乎没有地点"的阈值（占全部地点的比例）。
#: ★ 这是**唯一能从数据里读出"哪边是海"的信号**：没人住在海里。
# [EN] Threshold for "one side has almost no places" when judging a coastline. ★ This is the **only**
# [EN] signal in the data that says which side is sea: nobody lives in the sea.
WK_EMPTY_SIDE = 0.16

#: 判海岸线时，折线要横跨绘图区多大比例（太小的是河湾，不是海岸）。
# [EN] How much of the drawing area the line must span to count as a coast (small ones are inlets).
WK_SPAN_MIN = 0.55


#: "海味"地名用字：海边城镇的名字会带这些（**强信号**，比"一侧没地点"可靠）
# [EN] "Sea-flavoured" name characters; seaside towns carry them (a **strong** signal)
SEA_NAME_WORDS = ('海', '湾', '澳', '滩', '岛', '礁', '港', '浦', '洋')


def _sea_evidence(layout, pts) -> bool:
    """判"这是海岸线"的**旁证**：有海味地名，或原始折线超出了 0~1。

    ★ 为什么需要旁证：只用"一侧没地点"，沿河单岸的城镇会被判成海（实测误判，
      下半张图被填蓝）。旁证让这个判据从"猜"变成"有据"。
    ★ 为什么这两条就够：海边城镇几乎必然出现"海/港/湾"这类字（它们因海而存在），
      而海岸线的原始坐标常常画到 0~1 之外（AI 画"海"时本能地往图外延）。
      两条都不满足时**宁可按河画** —— 把河画成海会填蓝半张图。
    [EN] The **corroborating** evidence for "this is a coastline": a sea-flavoured place name, or the
    [EN] raw polyline going outside 0..1. ★ Why it is needed: with "one side empty" alone, a town on
    [EN] one river bank is judged a coast (measured: the lower half turned blue). ★ Why these two
    [EN] suffice: a seaside town almost always has 海/港/湾 in a name (it exists because of the sea),
    [EN] and a coastline's raw coordinates often run past 0..1 (AI extends "sea" off the sheet
    [EN] instinctively). When neither holds, **draw a river** -- a river drawn as a sea floods half the
    [EN] map with blue.
    """
    for p in (getattr(layout, 'places', None) or []):
        nm = str(getattr(p, 'name', '') or '')
        if any(k in nm for k in SEA_NAME_WORDS):
            return True
    for q in (getattr(layout, 'water', None) or []):
        try:
            if float(q[0]) < -0.001 or float(q[0]) > 1.001 \
                    or float(q[1]) < -0.001 or float(q[1]) > 1.001:
                return True
        except (TypeError, ValueError, IndexError):
            continue
    return False


def water_kind(layout, pts=None, box=None, *, places=None) -> str:
    """这条 `water` 是**河 / 湖 / 海**里的哪一种。

    Args:
        layout: `map_layout.Layout`（读它的 `water_kind` 声明）。
        pts:    折线的**屏幕坐标**（`px()` 之后）。不给就只按声明判。
        box:    绘图区矩形，用来判"贴不贴图廓"。
        places: 全部地点的**屏幕坐标**，用来判"哪一侧没人住"。

    Returns:
        `'river'` / `'lake'` / `'coast'`。

    ## 判法（按顺序，先判出来的赢）

    1. **上游声明优先**（`Layout.water_kind`，认 `river/lake/coast` 与 河/湖/海 等写法）；
    2. **闭合 ⇒ 湖**（首尾距离 ≤ 短边的 10%）；
    3. **两端贴图廓 + 横跨 ≥55% 图宽 + 一侧几乎没地点（≤16%）⇒ 海**；
    4. **其余 ⇒ 河**（含"判不准"）。

    ★ 第 3 条为什么需要"一侧没地点"：只看"两端贴图廓 + 横跨全图"的话，一条**斜穿
      整座城的河**也满足（很多城镇就是这么沿河建的）。加上"一侧没人住"才能把两者分开 ——
      河的两岸都有人，海的一侧没有。这一条**从数据推**，不靠猜。
    ★ 判不准一律给河：把河画成海会填蓝半张图，比把海画成河更错（后者只是少了信息）。
    [EN] Which of **river / lake / coast** this `water` is. Args: layout (reads its `water_kind`
    [EN] declaration); pts = the polyline in **screen coordinates**; box = the drawing area (to judge
    [EN] "touches the frame"); places = all places in **screen coordinates** (to judge "which side is
    [EN] uninhabited"). Returns `river`/`lake`/`coast`. Decision order: (1) the caller's declaration
    [EN] wins; (2) closed => lake; (3) both ends on the frame + spans >=55% of the width + one side has
    [EN] almost no places (<=16%) => coast; (4) otherwise river, **including "cannot tell"**.
    [EN] ★ Why (3) also needs "one side empty": "both ends on the frame and spans the map" alone also
    [EN] matches a river running diagonally across a town built along it (very common). "Nobody lives
    [EN] there" is what separates them -- a river has people on both banks, the sea does not. That is
    [EN] **read out of the data**, not guessed. ★ When unsure, always river: filling half the map blue
    [EN] is a worse error than drawing a sea as a river (the latter only loses information).
    """
    # ① 上游声明
    raw = str(getattr(layout, 'water_kind', '') or '').strip()
    if raw:
        k = _WK_ALIAS.get(raw.lower()) or _WK_ALIAS.get(raw)
        if k:
            return k
    if pts is None or len(pts) < 2 or box is None:
        return WK_RIVER
    x0, y0, x1, y1 = (float(v) for v in box)
    W, H = max(1.0, x1 - x0), max(1.0, y1 - y0)
    short = min(W, H)

    # ② 闭合 ⇒ 湖
    a, b = pts[0], pts[-1]
    if math.hypot(a[0] - b[0], a[1] - b[1]) <= max(10.0, 0.10 * short):
        return WK_LAKE

    # ③ 横跨够大 + **一侧几乎没地点** ⇒ 海
    #
    #   ⚠ 原来这里还要求"两端贴图廓"，实测**恒假**：水系坐标经 `frame_px` 映射后，
    #     端点常在框外上百像素（取景是按**地点**包围盒算的），`_on_frame` 永远不成立
    #     ⇒ 海边那份数据被判成河。判据要判**意图**（这条线把图分成陆与海），
    #     不要判"像素恰好落在框边"这种实现细节。
    # [EN] ⚠ This used to also require "both ends on the frame", which is **always false** in
    # [EN] practice: after `frame_px` the endpoints often sit a hundred pixels outside the box (the
    # [EN] framing is computed from the **places'** bounding box), so `_on_frame` never held and the
    # [EN] seaside data was judged a river. Judge the **intent** (this line divides land from sea),
    # [EN] not an implementation detail like "the pixel happens to lie on the frame edge".
    span = max(max(p[0] for p in pts) - min(p[0] for p in pts),
               max(p[1] for p in pts) - min(p[1] for p in pts))
    if span >= WK_SPAN_MIN * max(W, H):
        # 弦 a→b 把图分成两侧；数两边各有几个地点
        dx, dy = b[0] - a[0], b[1] - a[1]

        def _side(q) -> float:
            return dx * (q[1] - a[1]) - dy * (q[0] - a[0])

        if places:
            pos = [q for q in places if q is not None]
            if len(pos) >= 3:
                left = sum(1 for q in pos if _side(q) > 0)
                right = len(pos) - left
                if min(left, right) <= max(1, int(len(pos) * WK_EMPTY_SIDE)):
                    # ★★ "一侧没地点"**还不算证据**：沿河而建、全在一岸的城镇也满足
                    #   （实测：`临河铺/盐仓/米行/渡口` 全在河北岸 ⇒ 被判成海，整个下半张图被填蓝）。
                    #   必须再加一条**旁证**，二选一：
                    #     ① 有"海味"的地名（海/湾/澳/滩/岛/礁/港/浦）—— 海边城镇的名字会带这个；
                    #     ② 原始折线的坐标**超出 0~1**（海岸线常画到图外，河里少见）。
                    #   ⚠ 都没有 ⇒ 按河画。这是"判不准就当河"的落地。
                    # [EN] ★★ "One side has no places" is **not evidence by itself**: a town built
                    # [EN] along a river and entirely on one bank satisfies it too (measured:
                    # [EN] `临河铺/盐仓/米行/渡口` all north of the river were judged a coast and the
                    # [EN] whole lower half turned blue). A **corroborating** signal is required, one of:
                    # [EN] (1) a "sea-flavoured" place name (海/湾/澳/滩/岛/礁/港/浦) -- seaside towns
                    # [EN] carry it; (2) the raw polyline goes **outside 0..1** (a coastline is often
                    # [EN] drawn off the sheet, a river rarely is). ⚠ Neither => draw a river.
                    if _sea_evidence(layout, pts):
                        return WK_COAST
    return WK_RIVER


def clip_polyline(pts, box) -> list | None:
    """把折线裁到 `box` 内，返回**最长的那一段连续折线**（不足两个点返回 `None`）。

    ★ 为什么只要最长段：折线可能"穿出去又拐回来"（一条绕过山嘴的河），裁完会有好几段。
      画海岸线时取最长那段就够（其余段是同一片水的延伸，缺了不影响读）。
      真要做多段也可以，但没必要为罕见情形加一条会漂的路径。
    [EN] Clip a polyline to `box`, returning the **longest contiguous run** (or `None` if shorter
    [EN] than two points). ★ Why only the longest: a line can leave the frame and come back (a river
    [EN] rounding a headland) and produce several runs; for a coastline the longest is enough, and
    [EN] multi-run support would add one more path that can drift for a rare case.
    """
    runs: list[list] = []
    cur: list = []
    for k in range(len(pts) - 1):
        got = _clip_seg(pts[k], pts[k + 1], box)
        if got is None:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
            continue
        a, b = got
        if not cur or abs(cur[-1][0] - a[0]) > 0.5 or abs(cur[-1][1] - a[1]) > 0.5:
            if len(cur) >= 2:
                runs.append(cur)
            cur = [a]
        cur.append(b)
    if len(cur) >= 2:
        runs.append(cur)
    if not runs:
        return None

    def _len(run) -> float:
        return sum(math.hypot(run[i + 1][0] - run[i][0], run[i + 1][1] - run[i][1])
                   for i in range(len(run) - 1))

    return max(runs, key=_len)


def _rect_t(p, box) -> float:
    """矩形边界上一点 → **周长参数** t（`0` 在左上角，逆时针增加）。"""
    x0, y0, x1, y1 = box
    W, H = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
    x, y = float(p[0]), float(p[1])
    cand = [(abs(y - y0), x - x0),
            (abs(x - x1), W + (y - y0)),
            (abs(y - y1), W + H + (x1 - x)),
            (abs(x - x0), 2 * W + H + (y1 - y))]
    return min(cand)[1] % (2 * (W + H))


def _rect_at(t: float, box) -> tuple:
    """周长参数 t → 矩形边界上的点（`_rect_t` 的逆）。"""
    x0, y0, x1, y1 = box
    W, H = max(1e-6, x1 - x0), max(1e-6, y1 - y0)
    t %= 2 * (W + H)
    if t <= W:
        return (x0 + t, y0)
    t -= W
    if t <= H:
        return (x1, y0 + t)
    t -= H
    if t <= W:
        return (x1 - t, y1)
    t -= W
    return (x0, y1 - t)


def _rect_walk(ta: float, tb: float, box, *, forward: bool, n: int = 10) -> list:
    """沿矩形边界从 t=ta 走到 t=tb，返回**中间点**（不含两端）。

    ★ 围海域多边形要的就是"沿图廓绕过去"的那一段 —— 这是海岸线与图廓之间那块水面。
    [EN] Walk the rectangle boundary from t=ta to t=tb, returning the **intermediate points**
    [EN] (endpoints excluded). ★ This is the piece of frame you follow to close the sea polygon.
    """
    L = 2 * ((box[2] - box[0]) + (box[3] - box[1]))
    dt = ((tb - ta) % L) if forward else -((ta - tb) % L)
    if abs(dt) < 1e-9:
        return []
    return [_rect_at(ta + dt * (i + 1) / (n + 1), box) for i in range(n)]


def _extend_to_frame(p, q, box, *, reach: float = 6000.0):
    """从 `q` 经 `p` 继续延长，返回它与图廓的**远端交点**（`p` 已在框内时用）。

    ★ 为什么必须延长：海岸线的两端本来就该**走到图廓**（海一直延伸到图边）。
      不延长的话，折线停在框内，`sea_polygon` 只能把它与"最近的那条边"围起来 ——
      实测海域面积只有 **0.6%**，等于在海岸线下画了一条窄缝，读者看不到"海"。
    [EN] Extend from `q` through `p` and return the **far intersection** with the frame. ★ Why it is
    [EN] required: a coastline's ends should reach the neat line (the sea continues off the sheet).
    [EN] Without it the polyline stops inside the frame and `sea_polygon` can only enclose it against
    [EN] the nearest edge -- measured, the sea came out at **0.6%** of the area: a narrow sliver under
    [EN] the coastline instead of a sea.
    """
    dx, dy = p[0] - q[0], p[1] - q[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return None
    far = (p[0] + dx / L * reach, p[1] + dy / L * reach)
    got = _clip_seg(tuple(p), far, box)
    return tuple(got[1]) if got else None


def coast_line(pts, box) -> list:
    """海岸线的**实际画线**：裁到绘图区，两端再延长到图廓。

    ★ 为什么海岸线也必须延长：它的两端本来就该走到图边（海一直延伸到画幅之外）。
      只延长"海域面"而不延长"线"的话，蓝色水面比那条岸线长出一截 ——
      读者会看到"海从岸线外面涌出来"，岸边那一圈没有界线。
    ★ 一个函数、两处用（`draw_water` 画线、`sea_polygon` 围面），避免两套延长逻辑。
    [EN] The coastline **as drawn**: clipped to the drawing area, then both ends extended to the frame.
    ★ Why the line must be extended too: its ends belong on the frame (the sea runs off the sheet).
    [EN] Extending only the **area** makes the blue surface longer than the line, so the sea appears to
    [EN] spill past its own edge with no boundary at the shore. ★ One function, two users (`draw_water`
    [EN] draws the line, `sea_polygon` encloses the area) -- no second extension routine.
    """
    got = clip_polyline(pts, box)
    if got is None or len(got) < 2:
        return []
    ea = _extend_to_frame(got[0], got[1], box)
    eb = _extend_to_frame(got[-1], got[-2], box)
    if ea is not None and eb is not None:
        return [tuple(ea)] + [tuple(p) for p in got] + [tuple(eb)]
    return [tuple(p) for p in got]


def sea_polygon(pts, box, land=None) -> list:
    """海岸线 + 一段图廓围成的**海域多边形**（水在**远离陆地**的那一侧）。

    Args:
        pts:  海岸线的屏幕坐标折线。
        box:  绘图区。
        land: 陆地参考点（地点重心）。`None` 时用绘图区中心。

    Returns:
        多边形顶点（首尾不重复）。判不出返回空列表（调用方退回按河画）。

    ★ 为什么需要它：海是**面**不是线。没有这个多边形，海就只剩"沿一条线加粗的带"，
      读者看到的是沿海岸有一条蓝色的河（老实现的实际效果）。
    ★ 怎么定"哪边是海"：陆地点（`land`）在弦 a→b 的某一侧，海就在**另一侧** ——
      然后沿两条可能的路（顺时针/逆时针）走图廓，取中点落在海侧的那条。
      这是纯几何，没有"猜"的成分；两条都判不出时退回按河画，不硬编。
    [EN] The **sea polygon** enclosed by the coastline and a stretch of frame (water on the side
    [EN] **away from land**). Args: pts = coastline in screen coordinates; box = drawing area;
    [EN] land = a land reference point (centroid of places; defaults to the box centre). Returns
    [EN] polygon vertices, or an empty list when it cannot be decided (the caller then draws a river).
    [EN] ★ Why it is needed: the sea is an **area**, not a line. Without it the sea is only a
    [EN] thickened band along a line, which reads as "a blue river running along the shore" (what the
    [EN] old code actually drew). ★ How "which side is sea" is decided: the land point lies on one side
    [EN] of the chord a->b, so the sea is on the **other**; then walk the frame both ways and take the
    [EN] one whose midpoint lands on the sea side. Pure geometry, nothing guessed; if neither works we
    [EN] fall back to drawing a river rather than inventing a sea.
    """
    # 与画线**同一份**延长逻辑（`coast_line`），否则面与线会差一截
    # [EN] The **same** extension as the drawn line (`coast_line`), or the area and the line disagree
    got = coast_line(pts, box)
    if len(got) < 2:
        return []
    a, b = tuple(got[0]), tuple(got[-1])
    if math.hypot(a[0] - b[0], a[1] - b[1]) < 1.0:
        return []
    if land is None:
        lx, ly = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    else:
        lx, ly = float(land[0]), float(land[1])
    dx, dy = b[0] - a[0], b[1] - a[1]

    def _side(p) -> float:
        return dx * (p[1] - a[1]) - dy * (p[0] - a[0])

    s_land = _side((lx, ly))
    ta, tb = _rect_t(a, box), _rect_t(b, box)
    # ★★ 图廓这一段必须走 **b → a**（多边形是 a → 折线 → b → 沿图廓回 a → 闭合）。
    #   第一版取的是 a → b 的点序，接在 b 后面 ⇒ 多边形**自交**（从 b 斜穿回 a 附近，
    #   又把底边从左走到右）⇒ 用鞋带公式算出来净面积只剩 1%（两块正负相消）。
    #   而屏幕上看到的是"一块被折线划开的怪影子"，不是海。
    # [EN] ★★ This stretch of frame must run **b -> a** (the polygon is a -> polyline -> b -> back
    # [EN] along the frame -> close). The first version took the a -> b order and appended it after b,
    # [EN] so the polygon **self-intersected** (a diagonal from b back towards a, plus the bottom edge
    # [EN] left-to-right), and the shoelace area collapsed to 1% (two lobes cancelling). On screen that
    # [EN] is a stray shadow split by the coastline, not a sea.
    paths: list = []
    for fwd in (True, False):
        mid = _rect_walk(tb, ta, box, forward=fwd, n=10)
        if mid:
            paths.append(mid)
    best: list | None = None
    if not paths:
        return []
    if abs(s_land) < 1e-6:
        # 陆地重心正好落在弦上（罕见）：取"离陆地更远"的那条图廓路径
        best = max(paths, key=lambda q: math.hypot(
            q[len(q) // 2][0] - lx, q[len(q) // 2][1] - ly))
    else:
        for mid in paths:
            if _side(mid[len(mid) // 2]) * s_land <= 0.0:        # 中点与陆地**异侧** ⇒ 海侧
                best = mid
                break
    if not best:
        return []
    return [tuple(p) for p in got] + [tuple(p) for p in best]


def draw_water(shapes: list, layout, px, pal: dict, box: tuple, *,
               band: float = 16.0, places=None) -> dict:
    """画水系（**按类型分三路**）。返回 `{'kind': …, 'waters': bool}` 交给图例。

    Args:
        shapes: 图元列表（就地追加）。
        layout: 读 `water` / `water_kind`。
        px:     `Place → (x, y)` 的**唯一**换算（不在这里另算一遍）。
        pal:    调色板。
        box:    绘图区（同时是海域多边形的围合边界）。
        band:   河/湖画多宽（城市图比城际图宽一点）。
        places: 地点（判海时用来定"哪侧没人住"）；不给就只按声明与几何判。

    Returns:
        `{'kind': WK_*|'', 'waters': bool}`。

    ★ 为什么把这一段抽成一个函数：城市图与城际图**原来各写一份**（一份 22px 三层，
      一份 12~18px 两层），于是同一条河在两张图上画法不同、海岸线在一张上对一张上错。
      现在是**一个实现**，两张图只是 `band` 不同。
    [EN] Draw the water system, **routed by kind**. Returns `{'kind', 'waters'}` for the legend.
    [EN] ★ Why one function: the city and region maps **each had their own copy** (one 22px with three
    [EN] layers, one 12-18px with two), so the same river was drawn differently on the two maps and
    [EN] the coastline was right on one and wrong on the other. Now there is **one implementation**;
    [EN] the two maps differ only in `band`.
    """
    w = list(getattr(layout, 'water', None) or [])
    if len(w) < 2:
        return {'kind': '', 'waters': False}
    pts = [tuple(px(_P(a, b))) for a, b in w]
    ppos = [tuple(px(q)) for q in places] if places else None
    kind = water_kind(layout, pts, box, places=ppos)
    water = pal.get('water', '#8fb0c4')
    paper = pal.get('paper', '#f8f4ea')
    bank = pal.get('wall', '#b9b1a0')

    def _path_of(poly, *, close: bool = False):
        els = [fcv.Path.MoveTo(poly[0][0], poly[0][1])]
        els += [fcv.Path.LineTo(x, y) for x, y in poly[1:]]
        if close:
            els.append(fcv.Path.Close())
        return els

    if kind == WK_COAST:
        # 陆地参考点 = 地点重心（没有地点就用绘图区中心）
        land = None
        if ppos:
            land = (sum(q[0] for q in ppos) / len(ppos),
                    sum(q[1] for q in ppos) / len(ppos))
        poly = sea_polygon(pts, box, land)
        # ★ 自检：海域里**不许有地点**。有三点是"港城造在岸上"、越靠岸的越贴边，
        #   但**整个聚落落在海里**只可能说明这条线是河不是海岸 —— 那就退回按河画。
        #   这一条是判"横跨+一侧没地点"的必要补充：沿河而建、全在一岸的城镇会被前两条判成海。
        # [EN] ★ Self-check: the sea area must **not contain any place**. A port town's places sit on
        # [EN] the shore, hugging the edge, but a **whole settlement inside the sea** can only mean the
        # [EN] line is a river, not a coast -- so fall back to the river drawing. This complements
        # [EN] "spans the map + one side empty": a town built along a river entirely on one bank would
        # [EN] otherwise be judged a coast.
        _swallowed = [q for q in (ppos or []) if len(poly) >= 3 and pt_in_poly(q, poly)]
        # ⚠ 容差：落进海里的地点不超过 **20%** 就接受。理由有二 ——
        #   ① "哪侧是海"是用**弦**（a→b 连线）判的，而海岸线是折线，拐弯处个别点会落错侧；
        #   ② 填充画在 POI **之下**，被包住的点仍然看得见（读作"半岛上的那一处"）。
        #   全部地点都在海里（=城镇被淹）才说明这条线不是海岸线。
        # [EN] ⚠ Tolerance: accept when at most **20%** of the places fall inside the sea. Two
        # [EN] reasons: (1) "which side is sea" is judged from the **chord** (a->b) while the coastline
        # [EN] is a polyline, so a few points land on the wrong side at a bend; (2) the fill is drawn
        # [EN] **under** the POIs, so such a point stays visible (reads as "that spot on the
        # [EN] headland"). Only when **all** places are in the sea (the town is drowned) does it mean
        # [EN] this line is not a coastline.
        _worst = max(1, int(len(ppos or []) * 0.20))
        if len(poly) >= 3 and len(_swallowed) < max(1, min(_worst, len(ppos or []) or 1)) + 1:
            # ① 海面：浅蓝平涂（GB/T 20257.1 海部用浅蓝表示；不画等深线 —— 没有水深数据）
            # [EN] 1. Sea surface: a pale blue wash (GB/T 20257.1 shows the sea in pale blue; no
            # [EN] depth contours because we have no sounding data)
            shapes.append(fcv.Path(_path_of(poly, close=True), paint=ft.Paint(
                color=_mix(paper, water, 0.46), style=ft.PaintingStyle.FILL)))
            # ② 海岸线：**实线**（陆地与海的分界；虚线会被读成"界线/等深线"），
            #   两端**画到图廓** —— 与海域面用同一条延长过的线（`coast_line`）。
            # [EN] 2. Coastline: a **solid** line (the land/sea boundary; dashed reads as a border or a
            # [EN] depth contour), with both ends **reaching the frame** -- the same extended line the
            # [EN] sea area is built from (`coast_line`).
            _cl = coast_line(pts, box) or pts
            shapes.append(fcv.Path(_path_of(_cl), paint=ft.Paint(
                color=_mix(water, pal.get('ink', '#4a4f57'), 0.55), stroke_width=2.2,
                stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
            return {'kind': kind, 'waters': True, 'sea': list(poly),
                    'coast': [tuple(p) for p in _cl]}
        # 判不出海域多边形 ⇒ **按河画**（宁少一个面，不填错半张图）
        # [EN] No polygon => draw it as a river (better to miss a sea than fill the wrong half)
        kind = WK_RIVER

    if kind == WK_LAKE:
        # 湖：闭合填充 + 岸线（与海同一套，只是没有"一侧是海"的方向问题）
        # [EN] Lake: filled outline + shore line (same treatment as the sea, minus the "which side")
        shapes.append(fcv.Path(_path_of(pts, close=True), paint=ft.Paint(
            color=_mix(paper, water, 0.50), style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Path(_path_of(pts, close=True), paint=ft.Paint(
            color=_mix(water, pal.get('ink', '#4a4f57'), 0.55), stroke_width=1.6,
            stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
        return {'kind': kind, 'waters': True, 'lake': [tuple(p) for p in pts]}

    # 河：一条带。**两层**（先宽岸色、再窄水面）—— 原来是三层且顺序混乱
    # [EN] River: one band, **two layers** (wide bank colour, then narrower water) -- the old code had
    # [EN] three layers in a confusing order
    els = _path_of(pts)
    shapes.append(fcv.Path(els, paint=ft.Paint(
        color=bank, stroke_width=band + 3.0,
        stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
    shapes.append(fcv.Path(els, paint=ft.Paint(
        color=water, stroke_width=band,
        stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
    return {'kind': WK_RIVER, 'waters': True}


def _is_water(name: str) -> bool:
    """这是不是**水体**（河、湖、海、溪、渡），城际图上要画水面符号而不是聚落圆点。

    ⚠ `渡`/`津`/`港` 是**渡口/码头**，那是聚落（有人、有屋），不是水面 —— 排除掉。
      第一版没排，`渡口` 会被画成一片水，而它其实是"过河的地方"，图上有屋子。
    [EN] Is this **water** (river/lake/sea/stream) rather than a settlement? On the region map it
    [EN] gets a water symbol, not a town dot. ⚠ `渡`/`津`/`港` are **ferries/ports** -- settlements
    [EN] with people and buildings, not water -- so they are excluded; without that, `渡口` came out
    [EN] as a patch of water while it is actually "the place where you cross".
    """
    n = str(name or '')
    if any(k in n for k in ('渡', '津', '港', '码头', '桥')):
        return False
    return any(k in n for k in ('河', '江', '湖', '海', '溪', '潭', '泉', '湾'))


def _water_symbol(shapes: list, x: float, y: float, pal: dict) -> None:
    """水体符号：**三条短横波**（标准地图的水面记号），宽度向外递增。

    ★ 为什么不画成蓝色圆点：圆点在这张图上**已经**是"有人住的地方"的意思
      （`_town_symbol`）。同一种记号表示两件事，读者必然误读 —— 而"这条河有没有人住"
      是要拿来做判断的信息。
    [EN] Water symbol: **three short waves** (the standard water mark), widening outward. ★ Why not
    [EN] a blue dot: on this map a dot **already** means "people live here" (`_town_symbol`). One
    [EN] symbol for two meanings is guaranteed misreading, and "is there anyone living on this
    [EN] river" is information the reader makes decisions on.
    """
    col = pal.get('water', '#8fb0c4')
    w = 11.0
    for k, dy in enumerate((-3.4, 0.0, 3.4)):
        hw = w - k * 1.6
        shapes.append(fcv.Line(x - hw, y + dy, x + hw, y + dy,
                               paint=ft.Paint(color=col, stroke_width=1.6,
                                              stroke_cap=ft.StrokeCap.ROUND)))
