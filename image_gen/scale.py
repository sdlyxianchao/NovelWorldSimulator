"""**尺度分级** —— 同一处世界，三种看法。

## 为什么要分尺度

用户 2026-10-26：

> 「这个是建筑内部图 我想如果故事范围更大 我还希望由把房屋简略之后
>   绘制的城市地图（类似于高德地图那种） 城市之间的地图（类似标准地图 但是元素更少 ）」

这句话点出一个真问题：原来只有**两套画法**（室内平面 + 街道图），而"街道图"既要
顶城市、又要顶城际 —— 城际图被画成了城市街道图（把两座隔着五百里的城画成隔壁）。

三种尺度**不是同一张图缩放**，是三种不同的读法：

| 尺度 | 读者要回答的问题 | 必须有什么 | 必须没有什么 |
|---|---|---|---|
| `room` 室内 | 这屋里怎么走、人在哪间 | 墙、门、陈设、楼梯 | 街区、路网 |
| `city` 城市 | 从这儿到那儿怎么走、街区怎么分 | 街区面、分级路网、水系、地标 | 房间墙、家具 |
| `region` 城际 | 两城多远、路上经过什么 | 政区面、城镇节点、官道、山河 | 街道、房屋 |

## 判据（纯函数，不猜）

按**名字**与**用户/模型给的 `kind`** 判，三档都有明确的进入条件与退出条件：

1. `layout.kind` 明确写了 `'室内'`/`'局部'`/`'整体'` ⇒ 先按它初判（这是模型/作者的意图）；
2. 再用**名字**校正（`'室内'` 里出现「城」「州」「渡口」这种 → 说明其实是城际）；
3. 都没有依据 ⇒ `city`（**兜底给中间那档**：城市图对"一两个地点"和"十几个地点"
   都还能读，而室内图对十几个地点会挤成一团、城际图对一条街会空成白纸）。

## 与既有三级（`整体/局部/室内`）的关系

既有的 `mapanchor.LAYERS = ('整体','局部','室内')` 是**锚定的层名**，跟"画多大一片"
不是一回事（"局部"既可能是街角也可能是一个院）。这里不替换它，只加一层**渲染尺度**，
两者可以同时存在：锚定保证"同一处永远在同一格"，尺度决定"这一格画多少细节"。
"""
from __future__ import annotations

#: 四种尺度（**闭集**，别再加第五种而不改渲染层）
# [EN] Four scales (a closed set; adding a fifth requires touching the renderers)
ROOM = 'room'
CITY = 'city'
REGION = 'region'
#: ★★ 2026-10-26 新增 `deck`（甲板图）：**舟船的"室内"不是一间间房**。
#:
#: 为什么它必须单独一格、不能塞进 `room`：`roomplan` 解的是"矩形外轮廓里切房间
#: （分带＋拼满＋共用墙开门）"，而船是**狭长纵向分舱**、甲板是唯一的见天面、
#: 底舱无窗。同一套解算器画船，只能得到一艘"四合院形状的船"。
#: 为什么它也不能塞进 `city`：甲板上的"街"是舷侧通道，不是街区。
#: ⇒ 第三种读法，第四格。
# [EN] ★★ Added 2026-10-26: `deck`. A ship's "interior" is not a series of rooms. Why it cannot be
# [EN] `room`: `roomplan` solves "cut rooms inside a rectangular outline" (bands, full tiling, doors
# [EN] in shared walls), while a hull is **long and divided along the keel**, the deck is the only
# [EN] open-to-sky surface and the lower hold has no windows -- the same solver would yield "a ship
# [EN] shaped like a courtyard house". Why it cannot be `city`: a deck's "streets" are side passages,
# [EN] not blocks. => A third way of reading, a fourth slot.
DECK = 'deck'
ALL = (ROOM, CITY, REGION, DECK)

#: 中文标签（图例、日志、界面都用它，别在别处另写一套）
# [EN] Chinese labels; use these everywhere instead of a second copy of the strings
LABEL = {ROOM: '室内', CITY: '城市', REGION: '城际', DECK: '甲板'}

#: 各尺度"该画什么"的一句话（写进图例，让读者知道自己在看哪一种图）
# [EN] One line per scale for the legend, so the reader knows which kind of map this is
BLURB = {
    ROOM: '建筑内部平面：墙、门、陈设',
    CITY: '城市街道：街区、路网、水系、地标',
    REGION: '城际：城镇、官道、山川，不画街道与房屋',
    DECK: '船舶甲板平面：船体、舱壁、舱门，沿龙骨分舱',
}


#: **室内**证据：出现这些，几乎可以确定这是屋里/院内
# [EN] **Interior** evidence: these almost certainly mean indoors
ROOM_WORDS = ('堂', '厅', '室', '间', '厨', '灶', '厕', '浴', '卧', '书房', '柜台',
              '前厅', '后院', '天井', '厢房', '卧室', '客厅', '厨房', '阳台', '走廊',
              'hall', 'room', 'kitchen', 'bedroom', 'chamber', 'lobby', 'corridor')

#: **城际**证据：行政区划与远行设施。**只收强词**（≥2 字，或中文里几乎专属的字）。
#:
#: ⚠ 2026-10-26 实测踩到的：第一版把「河」「山」「道」「路」也收进来了，于是
#:   「临河茶肆 / 布庄 / 铁匠铺 / 渡口」这种**一条街**被判成了城际图 ——
#:   `临河` 贡献一个「河」、「渡口」贡献一个「渡」，两条就过线了。
#:   中文单字在街名里太常见，不能当行政证据（本项目老规矩：词表类匹配要看**边界**）。
#:   ⇒ 地形/水系的字单独放 `TERRAIN_WORDS`，**只加分、不能单独定档**。
# [EN] **Region** evidence: administrative units and long-distance infrastructure. **Strong words
# [EN] only** (>=2 chars, or characters that are nearly exclusive in Chinese).
# [EN] ⚠ Measured 2026-10-26: the first version also included 河/山/道/路, so a **single street**
# [EN] (临河茶肆 / 布庄 / 铁匠铺 / 渡口) came out as a region map -- `临河` gave one 河 and 渡口 one
# [EN] 渡, and two hits crossed the line. Chinese single characters are far too common in street
# [EN] names to serve as administrative evidence. => Terrain/water words live in `TERRAIN_WORDS` and
# [EN] may only add weight, never decide on their own.
REGION_WORDS = ('州', '府', '郡', '县', '关隘', '边关', '要塞', '驿', '驿站', '官道',
                '国境', '王城', '京师', '城池', '渡口', '津渡',
                'kingdom', 'empire', 'province', 'county', 'duchy', 'realm')

#: **地形/水系**证据：城际图上确实要画，但"河边的一间茶肆"也会命中 ⇒ 只能加分。
# [EN] **Terrain/water** evidence: it belongs on a region map, but "a teahouse by the river" hits it
# [EN] too => weight only.
TERRAIN_WORDS = ('山', '岭', '峰', '河', '江', '湖', '海', '溪', '谷', '原', '漠', '林',
                 'mountain', 'river', 'lake', 'sea', 'forest', 'desert', 'valley')

#: **城市**证据：街道设施、公共建筑（既不是屋里，也不是跨城）
# [EN] **City** evidence: street furniture and public buildings -- neither indoors nor inter-city
CITY_WORDS = ('街', '巷', '市', '集', '坊', '桥', '广场', '公园', '店', '铺', '楼',
              '局', '站', '口', '角', '码头', '祠', '庙', '寺', '观',
              'street', 'square', 'market', 'plaza', 'park', 'station', 'shop')


def _hits(name: str, words) -> int:
    n = str(name or '')
    return sum(1 for w in words if w and w in n)


def scale_of(layout, *, n_places: int | None = None, style=None) -> str:
    """判这一份布局该按**哪个尺度**画。

    Args:
        layout: `map_layout.Layout`（只要有 `kind` / `places` 两个属性就够，
                不要求是真类型 —— 判据喜欢喂简化对象）。
        n_places: 地点数（不给就从 `layout.places` 数）。
        style: `worldstyle.Style`。★ 给了才能判出 `deck`：舟船的"室内"不是房间，
               是**甲板分舱**，`kind='室内'` 对它同样是错的。

    Returns:
        `'room'` / `'city'` / `'region'` / `'deck'`。

    ## 判法（按顺序，先判出来的赢）

    0. **舟船 ⇒ `deck`**（2026-10-26 加）：`style.key == 'vessel'` 时直接给甲板图。
       ★ 这一条必须排在 `kind` 之前：`kind` 说的是"室内/整体"这种**陆地**意图，
         对一条船没有意义（船上每一层都是"室内"）。排在后面就永远轮不到它。
    1. **`kind` 是硬意图**：`'室内'` → room；`'整体'` → 先看名字，名字里没有
       「城州府郡关渡驿」这种 → **region 降级成 city**（很多人把"一整条街"写成"整体"）；
    2. **名字投票**：室内证据 ≥2 且压过城际 ⇒ room；城际证据 ≥3 且压过室内 ⇒ region；
    3. **数量兜底**：≥8 个地点且城际词少 ⇒ city（十几个点是"一片街区"）；
    4. 都不成立 ⇒ **city**（中间那档最不容易读错）。

    ★★★ 为什么 `kind='整体'` 不直接等于 region：既有代码里 `'整体'` 表示"不画室内、
      只标记建筑"，实测就是**城镇街道图**（`_draw_street` 那条路）。
      把它一律当城际，会把"一条街"画成"两个国家的边境界图"。所以要看名字。

    [EN] Decide which **scale** this layout should be drawn at. ## Rules (in order, first match
    [EN] wins): 1) `kind` is a hard intent (`'室内'` -> room; `'整体'` -> look at names first, and if
    [EN] no 城州府郡关渡驿 appears, **demote region to city**, because many callers write "whole" for
    [EN] "one street"); 2) name voting (>=2 interior words beating region -> room; >=3 region words
    [EN] beating interior -> region); 3) count fallback (>=8 places with few region words -> city);
    [EN] 4) otherwise **city**, the middle tier that misreads least.
    [EN] ★★★ Why `kind='整体'` is not simply region: in the existing code it means "no interior, just
    [EN] building markers", i.e. a **town street map** (`_draw_street`). Treating it as region would
    [EN] draw "one street" as a border map between two countries. So names decide.
    """
    places = list(getattr(layout, 'places', None) or [])
    n = len(places) if n_places is None else int(n_places)
    names = [str(getattr(p, 'name', '') or '') for p in places]
    blob = ' '.join(names)
    kind = str(getattr(layout, 'kind', '') or '')

    # ⓿ 舟船 ⇒ 甲板图（必须在 `kind` 之前，见 docstring）
    # [EN] 0. A ship => deck plan (before `kind`; see the docstring)
    if str(getattr(style, 'key', '') or '') == 'vessel':
        return DECK

    in_room = _hits(blob, ROOM_WORDS)
    in_reg = _hits(blob, REGION_WORDS)
    in_terr = _hits(blob, TERRAIN_WORDS)      # 地形只加分，不单独定档
    in_city = _hits(blob, CITY_WORDS)

    # ① `kind` 硬意图
    if kind == '室内':
        # ⚠ 但要有反证出口：`kind='室内'` 而名字全是「青州」「云中府」⇒ 明显标错了。
        #   门槛取 **2** 而不是 3：两个都是州府级已经很硬（`青州`+`云中府` 一起出现，
        #   不可能是屋里两间房的名字）。取 3 会让这种明显错标一路画成平面图。
        # [EN] There must be an escape hatch: `kind='室内'` while every name is `青州`/`云中府` is
        # [EN] clearly mislabelled. The bar is **2**, not 3: two prefecture-level names together
        # [EN] cannot be two rooms in a house, and a bar of 3 would let that slip through as a plan.
        if in_reg >= 2 and in_reg > in_room:
            return REGION
        return ROOM
    if kind == '整体':
        # 行政强词 ≥2 ⇒ 城际；只有地形词（河山）**不够**，那多半是"河边的镇子"
        # [EN] Two strong administrative words => region; terrain alone (river/hills) is **not
        # [EN] enough -- that is usually "a town by the river".
        if in_reg >= 2 or (in_reg >= 1 and in_terr >= 2 and in_city == 0):
            return REGION
        return CITY            # ← 只标记建筑的一大片 = 城镇街道图（既有语义）

    # ② 名字投票
    if in_room >= 2 and in_room > in_reg:
        return ROOM
    if in_reg >= 2 and in_reg > in_room:
        return REGION
    if in_reg >= 1 and in_terr >= 2 and in_city == 0 and in_room == 0:
        return REGION

    # ③ 数量兜底
    if n >= 8 and in_reg <= 1:
        return CITY

    # ④ 兜底
    return CITY


def floor_label(fl: int) -> str:
    """层号的显示名：`-1` → `B1`，`0/1` → `1层`，`2` → `2层`。

    ★ 地下层用负数（`roomplan.floor_of` 给的），显示成本领域的惯例 `B1/B2`。
      直接显示 `-1层` 是程序员写法，读者要愣一下。
    [EN] Display name for a floor number: -1 -> B1, 0/1 -> 1层, 2 -> 2层. ★ Underground floors use
    [EN] negative numbers (`roomplan.floor_of`); display them as B1/B2 (the convention readers
    [EN] expect). Showing "-1层" makes the reader stop and decode it.
    """
    try:
        n = int(fl)
    except (TypeError, ValueError):
        n = 1
    if n < 0:
        return f'B{-n}'
    return f'{max(1, n)}层'


# ══════════════════════════════════════════════════════════════════════
#  道路分级（标准地图的核心约定）
# [EN] Road classification (the core convention of standard cartography)
# ══════════════════════════════════════════════════════════════════════
#: 道路等级（**闭集**，从高到低）。标准地图的道路是有**等级体系**的，
#: 不是"一条线画多粗"随手定 —— 分级决定：线宽、双线还是单线、有没有中心线。
# [EN] Road classes (**a closed set**, high to low). Roads on a standard map form a **hierarchy**,
# [EN] not a hand-picked line width: the class decides width, double vs single line, and whether a
# [EN] centre line is drawn.
RC_TRUNK = 'trunk'      # 主干道／官道：双线带 + 中心线
RC_MAIN = 'main'        # 次干道：双线带
RC_LOCAL = 'local'      # 支路／小巷：细双线
ROAD_CLASSES = (RC_TRUNK, RC_MAIN, RC_LOCAL)

#: 各等级的**画法参数**：`(外宽, 内宽, 有没有中心线)`。
#: ⚠ 数值是"视觉合适"，不是真实路宽 —— 我们没有尺寸数据，写真实米数就是编。
#: [EN] Drawing parameters per class: `(outer width, inner width, has centre line)`.
#: ⚠ The numbers are "visually sensible", not real widths -- we have no dimension data, and writing
#: real metres would be fabrication.
ROAD_SPEC = {
    RC_TRUNK: (13.0, 9.0, True),
    RC_MAIN: (9.0, 6.0, False),
    RC_LOCAL: (6.0, 3.6, False),
}

#: 各等级在图上的说明（图例用，**只描述画法**，不假装知道路名/编号）
# [EN] Legend text per class (describes the drawing only; never pretends to know names or numbers)
ROAD_LABEL = {
    RC_TRUNK: '主干道（连两处要地）',
    RC_MAIN: '次干道',
    RC_LOCAL: '支路 / 小巷',
}


#: 各尺度里"最高一级"是几号。★ 这是**唯一**该定义"什么是最高级"的地方。
#: 城市尺度：`size` 分 小1/中2/大3/特大4，而 `特大` 极少出现 ⇒ 最高级取 **3（大）**。
#: 城际尺度：`settlement_rank` 4=都城州府、3=县城要塞、2=镇驿、1=村渡 ⇒ 最高级取 **4**。
#: ⚠ 不给这个参数就会出两种错：门槛写 4 时城市图**永远没有主干道**（实测：大—大 只判成次干道）；
#:   写 3 时城际图把"县城—县城"当成主干道。
# [EN] Which rank counts as "the top tier" at each scale. ★ This is the **only** place that
# [EN] definition should live. City scale: `size` is 小1/中2/大3/特大4 and 特大 is rare, so the top
# [EN] tier is **3 (大)**. Region scale: `settlement_rank` is 4=capital/prefecture, 3=county/fortress,
# [EN] 2=town/post, 1=village => top is **4**. ⚠ Without this parameter two errors appear: with a
# [EN] hard 4 the city map **never produces a trunk road** (measured: 大—大 graded as main); with a
# [EN] hard 3 the region map calls "county to county" a trunk.
TOP_CITY = 3
TOP_REGION = 4


def road_class(rank_a: int, rank_b: int, *, top: int = TOP_REGION) -> str:
    """按**两端的重要度**定这条路属于哪一级。

    Args:
        rank_a / rank_b: 两端的等级（城市图用 `SIZE_W` 1~4；城际图用 `settlement_rank` 1~4）。

    Returns:
        `'trunk'` / `'main'` / `'local'`。

    * `top`: 该尺度的最高级（城市图 `TOP_CITY=3`、城际图 `TOP_REGION=4`）。

    ## 判法（可解释，三档）

    * 两端**都**在最高级 ⇒ `trunk`：两处要地之间的主通道；
    * 任一端 ≥ 最高级 − 1 ⇒ `main`：一条主要道路；
    * 其余 ⇒ `local`。

    实测两个尺度都对（这就是为什么门槛必须由调用方给，不能写死）：
      城市 `top=3`：大—大=trunk · 大—中=main · 中—中=main · 小—小=local
      城际 `top=4`：州府—州府=trunk · 州府—县城=main · 县城—县城=main · 镇—镇=local

    ★★ 为什么用"两端重要度"而不是给每条路单独存等级：
      我们**没有**道路等级数据（没有路网表、没有编号）。但"这条路通往哪儿"是
      **可以推**的 —— 一条连着州府与关隘的路，在任何地图上都会比"村里到田里"宽。
      这是**相对**信息，不是编造；而给每条路编一个"国道 305"就是编造。
    ★★ 为什么必须在**一处**定义：城市图和城际图原来各算一套宽度
      （`5.0 + 2.6 * 端点size` / `2.0 + 1.6 * 端点rank`），于是同一条路在两张图上
      粗细比例不一致 —— 而这两张图是**同一份 `links`**。老规矩：两处实现必然漂。
    [EN] Classify a road by **how important its two ends are**. Rules: both ends at the top tier
    [EN] (>=4) => trunk; either end >=3, or the sum >=5 => main; otherwise local.
    ★★ Why importance rather than a stored class per road: we have **no** road-class data (no
    [EN] network table, no route numbers), but "where does this road lead" **can** be inferred -- a
    [EN] road joining a prefecture and a pass is wider than a village-to-field track on any map. That
    [EN] is **relative** information, not fabrication; inventing "National Route 305" for each road
    [EN] would be. ★★ Why it must live in **one** place: the city and region maps each computed their
    [EN] own width (`5.0 + 2.6 * end size` vs `2.0 + 1.6 * end rank`), so the same road had a
    [EN] different thickness ratio on the two maps -- while both are the **same `links`**. Two
    [EN] implementations always drift.
    """
    a, b = int(rank_a or 1), int(rank_b or 1)
    t = max(2, int(top or TOP_REGION))
    if a >= t and b >= t:
        return RC_TRUNK
    if max(a, b) >= t - 1:
        return RC_MAIN
    return RC_LOCAL


def rank_bands() -> list:
    """各等级在图例里的次序（高→低）。
        English: Class order for the legend (high to low).
    """
    return list(ROAD_CLASSES)


# ══════════════════════════════════════════════════════════════════════
#  取景：地点实际占了多大一片（**只看有多大，不改坐标**）
# [EN] Framing: how much ground the places actually occupy (size only, coordinates untouched)
# ══════════════════════════════════════════════════════════════════════
#: 取景时四周留出的边距（占地点跨度的比例）。留给标签与指北针。
# [EN] Margin left around the framed extent (as a fraction of the places' span), for labels and the
# [EN] north arrow.
FRAME_MARGIN = 0.12

#: 跨度小于这个值就撑到这么大 —— 防止"所有地点挤在一处"时缩放爆炸（除零/天文数字）。
# [EN] Below this span, widen to it -- otherwise "all places in one spot" explodes the scale.
FRAME_MIN_SPAN = 0.06


def layout_extra(layout) -> list:
    """这张图**除地点之外**还要取进画面的东西：水系折线、院墙轮廓（裸坐标对）。

    ★ 为什么要一个函数：大地图（`floorplan`）与小地图（`minimap`）都要用同一份 ——
      各写一遍就会漂，而漂的后果是"小图上有海、大图上没有"（用户报过两次类似的）。
    ★ 这里只**读**属性，不认类型（`layout` 可以是任何带 `water` / `walls` 的对象，
      判据喜欢喂简化对象）。取不到就给空 —— 取景少了水，最坏是水在图外，
      不会让整张图崩。
    [EN] What this map must frame **besides the places**: water polylines and wall outlines, as bare
    [EN] coordinate pairs. ★ Why a function: both the big map (`floorplan`) and the minimap consume it
    [EN] and two copies always drift -- the symptom would be "the small map has the sea, the big one
    [EN] does not". ★ It only **reads** attributes and never checks the type (criteria like to pass
    [EN] simplified objects). Missing attributes give an empty list: framing less is the worst case.
    """
    out: list = []
    for key in ('water', 'walls'):
        for q in (getattr(layout, key, None) or []):
            if q is not None and len(q) >= 2:
                out.append((float(q[0]), float(q[1])))
    return out


def tight_bounds(places, *, margin: float | None = None, also=None) -> tuple:
    """这批地点**实际占的那一块**（归一化坐标，已含边距）；`(x0, y0, x1, y1)`。

    ## 为什么需要它（2026-10-27，用户："现有地图重新绘制"时量出来的）

    城市图/城际图的取景原来是"整个绘图区 = 归一化 0~1"，也就是**假定位点铺满全图**。
    而真实数据里 AI 给的坐标常常挤在中间一小块：实测那份当天地图的 6 处地点
    只用了绘图区的 **34% × 37%** —— 画出来是"中间一坨、四周一大片空街区"，
    读者既看不出相对方位，也不知道这片空白是什么。

    ★ 这不是"编坐标"：坐标原样不动，只是把**看多大一片**改成"地点实际所占"
      （地图缩放本来就是这个意思）。所以它与"不编造"不冲突。
    ★ 留 `margin` 的边距给标签用：不留的话贴边的名字会被画到框外。
    ★ 地点只有一个（或全在同一处）时撑到 `FRAME_MIN_SPAN`，否则缩放会爆炸。

    [EN] The block of ground these places **actually occupy** (normalised, margins included).
    ## Why (measured 2026-10-27 while re-drawing the live maps): the city/region framing used to be
    [EN] "the whole drawing area = 0..1", i.e. it assumed the spots fill the picture. Real AI-given
    [EN] coordinates often huddle in the middle -- measured, the six places of that day's map used only
    [EN] **34% x 37%** of the drawing area, so the result was "a blob in the middle and a large empty
    [EN] block field around it", conveying neither bearings nor what the blank was. ★ Not fabrication:
    [EN] coordinates are untouched; only **how much ground is framed** changes (which is what zooming a
    [EN] map means). ★ `margin` keeps room for labels, or edge labels get drawn outside the frame.
    [EN] ★ A single place (or all in one spot) widens to `FRAME_MIN_SPAN`, or the scale explodes.
    """
    ps = [p for p in (places or []) if p is not None]
    # ★★★ 2026-10-27（用户：「如果是海边等位置 看下是否可以正常绘制海岸线」）：
    #   取景原来**只按地点**算，于是水系（河/海岸线/院墙）只要超出地点包围盒，
    #   就会被映射到框外远远的地方 —— 实测一份海边数据：地点 y 在 0.10~0.28，
    #   海岸线 y≈0.6 被映射到 **y≈1079**，而画布只有 602 高 ⇒ 整条海岸线在图外，
    #   图上**一个水元素都没有**。这不是画法问题，是取景把它整个排除了。
    #   ⇒ `also` 收"同样属于这张图的东西"（裸坐标对，不是 `Place`）：
    #     地图上画了什么，取景就要包含什么。少一个，那块内容就凭空消失。
    # [EN] ★★★ 2026-10-27 (the user: "check whether a coastline draws properly at seaside
    # [EN] locations"): framing used to consider **places only**, so anything else (river, coastline,
    # [EN] courtyard wall) that fell outside their bounding box was mapped far outside the frame --
    # [EN] measured on a seaside layout: places at y 0.10-0.28, the coastline at y~0.6 mapped to
    # [EN] **y~1079** on a 602-tall canvas, i.e. entirely off-canvas and **not one water element on the
    # [EN] picture**. That is not a drawing problem; framing excluded it outright. => `also` takes
    # [EN] "things that also belong to this map" (bare (x, y) pairs, not `Place`): frame whatever the
    # [EN] map draws. Miss one and that content vanishes.
    extra = [(float(q[0]), float(q[1])) for q in (also or [])
             if q is not None and len(q) >= 2]
    if not ps and not extra:
        return (0.0, 0.0, 1.0, 1.0)
    xs = [float(getattr(p, 'x', 0.5) or 0.0) for p in ps] + [q[0] for q in extra]
    ys = [float(getattr(p, 'y', 0.5) or 0.0) for p in ps] + [q[1] for q in extra]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    # 撑到最小跨度（以包围盒中心为准，两边各撑一半）
    if x1 - x0 < FRAME_MIN_SPAN:
        c = (x0 + x1) / 2.0
        x0, x1 = c - FRAME_MIN_SPAN / 2.0, c + FRAME_MIN_SPAN / 2.0
    if y1 - y0 < FRAME_MIN_SPAN:
        c = (y0 + y1) / 2.0
        y0, y1 = c - FRAME_MIN_SPAN / 2.0, c + FRAME_MIN_SPAN / 2.0
    m = FRAME_MARGIN if margin is None else max(0.0, float(margin))
    mx = (x1 - x0) * m
    my = (y1 - y0) * m
    return (x0 - mx, y0 - my, x1 + mx, y1 + my)


def frame_px(places, box: tuple, *, margin: float | None = None, also=None):
    """把归一化坐标映射进 `box = (x0, y0, x1, y1)` 的**紧凑取景**换算函数。

    ★ 为什么把它做成一个函数工厂，而不是在调用处各写一遍线性变换：
      本项目《两处实现必然漂》——大地图与小地图必须用**同一个式子**，
      否则同一天的两张图点位不一致（用户："小图和大图不像"）。
    ★ `box` 是像素矩形（绘图区），`tight_bounds` 给的是归一化矩形；两者不要混。
    ★ `also` = 同样要取进画面的**裸坐标点**（水系折线、院墙）——
      不给它，水就会被映射到框外（见 `tight_bounds` 的说明）。

    [EN] A mapping from normalised coordinates into the pixel rectangle `box` using **tight
    [EN] framing**. ★ Why a factory instead of writing the linear transform at each call site: this
    [EN] project's "two implementations drift" rule -- the big and small maps must use **one formula**,
    [EN] or the two pictures of the same day disagree (the user: "the minimap and the big map do not
    [EN] look alike"). ★ `box` is pixels; `tight_bounds` returns normalised coordinates. Do not mix.
    """
    bx0, by0, bx1, by1 = (float(v) for v in box)
    tx0, ty0, tx1, ty1 = tight_bounds(places, margin=margin, also=also)
    dx = (tx1 - tx0) or 1.0
    dy = (ty1 - ty0) or 1.0

    def px(p) -> tuple:
        u = (float(getattr(p, 'x', 0.5) or 0.0) - tx0) / dx
        v = (float(getattr(p, 'y', 0.5) or 0.0) - ty0) / dy
        return (bx0 + u * (bx1 - bx0), by0 + v * (by1 - by0))

    return px
