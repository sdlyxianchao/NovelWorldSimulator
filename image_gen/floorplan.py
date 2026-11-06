# -*- coding: utf-8 -*-
"""**大地图**的矢量绘制：按"标准平面图 / 普通地图"的画法画细一档（用户 2026-10-12 点名）。

用户原话（这一整段就是规格）
--------------------------
    「我希望画 2 个地图
      1 个是显示在运行界面的小地图 在左边 不需要那么精细
      还一个是这个小地图可以点 我点了之后打开一个**大地图对话框**（比较大的大小，
      跟对话列表的部分一样大）到那时是一个**独立的对话框** 点了之后可以看到
      **详细的地图**（这个地图按照**标准室内装修或者室外普通地图的绘制方法**绘制，
      但是可以进行一些**简化**）
      地图**左上角带基本信息** 包括**地点 时间 图例 比例尺**（按照地图的方法
      在**一个方框里**）然后**右上角有关闭按钮**
      所有的地图保存在本地如果后续场景能够复用的话则直接复用」

所以这个模块和小地图是**同一份数据的两种画法**，不是两份数据：
  · 小地图（`minimap.build_shapes`）—— 196×132，能省就省，**只要能认出"在哪儿"**；
  · 大地图（本模块）—— 940×600，按平面图的规矩来：**墙有厚度、门有开口、
    家具有记号、图上有图例与比例尺**。

两者**共用同一个细致程度判定**（`minimap.detail_of`）—— 小图和大图
不能一个当"室内"、一个当"街道"，那会让人以为它们画的是两个地方。

画的规矩（"可以进行一些简化"落到这里的四条）
------------------------------------------
1. **墙画两条线**（双线 = 有厚度），不是小地图那种一根细线；
2. **门画成缺口 + 一道开合弧**（平面图的标准记号），不是写个"门"字；
3. **家具/陈设画成带阴影斜线的方块**（柜台、条案都这么标）；
4. **院里铺细点**（室外地面）、**水面画波纹**（水系的记号）。

⚠ 四条**只做记号，不做尺寸标注** —— 我们没有真实尺寸，编一个"3.2 米"
  就是**编**（这个项目最忌讳这个）。所以比例尺那一栏照实写「示意」。

English:
**Vector drawing of the big map**: drawn one notch finer following "standard floor plan / ordinary
map" conventions (the user named this on 2026-10-12).
The user's exact words (this whole passage is the spec)
--------------------------
    "I want two maps drawn:
      1 is the minimap shown in the run UI, on the left, it doesn't need to be that fine;
      and the other is that this minimap can be clicked -- when I click it, a **big map dialog** opens
      (a fairly large size, the same size as the conversation-list part), at that point it is an
      **independent dialog**, and after clicking you can see a **detailed map** (this map is drawn
      following the **standard interior-decoration or ordinary outdoor map drawing method**, though it
      can be **simplified**);
      the map carries **basic information in its top-left**, including **location, time, legend, scale
      bar** (**in a box**, the way maps do it), and then **a close button in the top-right**;
      all maps are saved locally, and if a later scene can reuse one, just reuse it."
So this module and the minimap are **two drawings of the same data**, not two datasets:
  · the minimap (`minimap.build_shapes`) -- 196x132, sparing wherever possible, **just enough to
    recognize "where you are"**;
  · the big map (this module) -- 940x600, following floor-plan conventions: **walls have thickness,
    doors have openings, furniture has symbols, and the map has a legend and a scale bar**.
The two **share one level-of-detail decision** (`minimap.detail_of`) -- the small and big maps must
not treat one as "indoor" and the other as "street"; that would make people think they depict two
different places.
The drawing conventions ("it can be simplified" comes down to these four here)
------------------------------------------
1. **Walls are two lines** (a double line = thickness), not the minimap's single thin line;
2. **Doors are drawn as an opening + a swing arc** (the standard floor-plan symbol), not the
   character "门";
3. **Furniture/fixtures are blocks with a hatched shadow** (counter and side table are both marked
   this way);
4. **The courtyard is stippled** (outdoor ground) and **water gets ripples** (the water symbol).
⚠ These four **only make marks, never dimension annotations** -- we have no real dimensions, and
  inventing "3.2 metres" would be **fabrication** (the biggest taboo in this project). So the scale
  row truthfully says "schematic".
"""
from __future__ import annotations

import math

import flet as ft
import flet.canvas as fcv

from image_gen import minimap as MM
from image_gen import plan_audit as PA
from image_gen import roomplan as RP
from image_gen import scalemap as SM
from image_gen import furniture as FR
from image_gen import scale as SC
from image_gen import worldstyle as WS
from image_gen import label_place as LP
from image_gen.map_layout import Layout, Place

# ★ 图上那些**给人看的字**（图例、信息框的字段名）走 `t()`，英文界面下才对得上。
#   ⚠ 只能**在这里**（模块级）引 `i18n`：它是零依赖的顶层模块
#     （`i18n.py` 一个 import 都没有），所以不会成环。
#     画布的 `Text` 不在控件树里，`verify_ui_english` 那种"扫控件树"的判据
#     看不见它 —— 那正是这里要主动做对的原因（判据看不见 ≠ 用户看不见）。
# [EN] ★ The **human-readable text** on the map (legend, info-box field names) goes through `t()`
# [EN] so it matches under the English UI.
# [EN]   ⚠ `i18n` may only be imported **here** (at module level): it is a zero-dependency top-level
# [EN]     module (`i18n.py` has not one import), so no cycle.
# [EN]     Canvas `Text` is not in the control tree, and "walk the control tree" criteria like
# [EN]     `verify_ui_english` cannot see it -- which is exactly why this must be done right
# [EN]     deliberately (criteria can't see it != the user can't see it).
from i18n import t

# ── 配色：与小地图同一套默认（调用方传界面那套进来覆盖）──────────────
# [EN] ── palette: the same defaults as the minimap (the caller passes the UI's own to override) ──
PALETTE = dict(MM.PALETTE)
PALETTE.update({
    'grid': '#eae3d4',       # 测绘纸的淡格
    'wall_hi': '#6b5a44',    # 墙体（双线）
    'ground': '#f3eee2',     # 室外地面
    'furniture': '#cfc4ad',  # 家具填充
    # [EN] furniture fill
})

#: 画布默认尺寸。**跟着对话框走**：对话框 1000×700（与日志/对话栏同级），
#: 去掉纸框内边距与标题行，画布给 940×600 —— 再大就要在对话框里出现滚动条了。
# [EN] : default canvas size. **Follows the dialog**: the dialog is 1000x700 (the same tier as the
# [EN] log / conversation pane), and after removing the paper frame's padding and the title row the
# [EN] canvas gets 940x600 -- any larger and a scrollbar appears inside the dialog.
W, H = 940, 600

#: 信息框（左上角那一块）的几何。
# ★ 2026-10-12：**不再是一个方框**了（用户：「左上角的图例 不要带方框了
#   但是要注意地图部分不要跟图例重合」）。它现在只是"图例区"——
#   不画边框，但仍然**占住**这块地方，绘图区从它右边开始（这就是"不重合"的保证）。
# [EN] : geometry of the info box (the top-left block).
# [EN] ★ 2026-10-12: it is **no longer a box** (the user: "the legend in the top-left should not have
# [EN] a box, but note that the map part must not overlap the legend"). It is now just the "legend
# [EN] area" -- no border drawn, but it still **occupies** this space and the drawing area starts to
# [EN] its right (that is the guarantee of "no overlap").
INFO_W, INFO_H = 268, 148
INFO_PAD = 12

#: 平面图房间矩形的**初始胖瘦**（占绘图区的比例）。
# ★ 2026-10-12 从 0.26 调小到 0.17：0.26 太胖 —— 只有一间房时没有任何东西约束它，
#   于是房间框几乎铺满整张图，把院子挤到角上，**必然重叠**（用户报的那个）。
#   0.17 让房间是个"房间"而不是"半张图"。
# [EN] : the **initial fatness** of a floor-plan room rectangle (fraction of the drawing area).
# [EN] ★ 2026-10-12 lowered from 0.26 to 0.17: 0.26 was too fat -- with one room nothing constrains
# [EN] it, so the room box filled almost the whole map, squeezed the courtyard into a corner and
# [EN] **inevitably overlapped it** (what the user reported). 0.17 keeps a room a "room" instead of
# [EN] "half the map".
PLAN_GROW = 0.17

#: 比例尺的位置：**图例下面**（用户 2026-10-24：「大地图比例尺又被挡住了
#  请把比例尺后续就放到图例的下面」）。
#
#  ★★★ 为什么不能留在左下角：那里是**底纹与地图内容的下沿**，比例尺虽然最后画
#  （永远在最上层），但一块"贴在别的线条上的白底尺"看着就是被压住了 ——
#  2026-10-22 修过一次（把底纹收进绘图区），2026-10-24 用户又看到它被挡。
#  左边那一列（图例区）是**从来没有别的东西**的地方：图例占住它、绘图区从它右边
#  开始，比例尺接在图例最后一条下面，就再没有东西可以压它。
#  ⇒ 纵向位置**不再是一个写死的 y**：由 `scale_origin()` 按图例条目数算出来，
#    产品与判据共用那一份（不共用就会漂，见 `layout_area` 的说明）。
# [EN] Where the scale bar sits: **below the legend** (the user on 2026-10-24: "the big map's scale
# [EN] bar is covered again -- from now on put the scale bar below the legend").
# [EN] ★★★ Why it cannot stay in the bottom-left: that is where the underlay and the map content's
# [EN] lower edge live. The scale is drawn last (always on top), but a white-backed ruler sitting on
# [EN] other lines simply reads as "covered" -- we fixed that once on 2026-10-22 by confining the
# [EN] grid, and on 2026-10-24 the user saw it covered again. The left column (the legend area) is the
# [EN] one place where nothing else is ever drawn: the legend owns it and the drawing area starts to
# [EN] its right, so a scale bar right below the last legend entry has nothing to be covered by.
# [EN] => The vertical position is **no longer a hardcoded y**: `scale_origin()` computes it from the
# [EN] number of legend entries, and the product and the criteria share that one definition.
SCALE_X = 12.0 + INFO_PAD

#: 比例尺那一块**整体**多高：标题 13 + 尺 9 + 刻度字 12。
# [EN] : how tall the whole scale block is -- a 13px title + a 9px ruler + 12px of graduations.
SCALE_BLOCK_H = 13 + 9 + 12

#: 图例最后一条文字与比例尺标题之间的缝。
# [EN] : the gap between the last legend entry and the scale bar's title.
SCALE_GAP = 10.0

#: 绘图区离画布**下沿**留的白。
#  比例尺搬走之后这里不再需要 46 那么多（那是给"标题 13 + 尺 9 + 刻度 12 + 缝"倒推的），
#  但仍要留一圈呼吸位，并且给右下角的指北针一点余地。
# [EN] : the padding between the drawing area and the canvas **bottom**. With the scale bar moved
# [EN] away this no longer needs to be 46 (that was derived from title 13 + ruler 9 + graduations 12 +
# [EN] gap); it still keeps a margin, and leaves some room for the north arrow in the bottom-right.
BOTTOM_PAD = 26.0

#: 图例区里各行的**行距**（标题 / 时间 / 细致程度 / 「图例」那行标题 / 每条图例）。
#  ★ 这三个以上的数在 `_info_box`（逐行往下排）和 `legend_height()`（算总高）里
#    都要用 —— 以前两处各写一份字面量，改一处必漂 15px。
# [EN] : the line steps inside the legend area (title / time / level of detail / the "legend" heading
# [EN] / each entry). ★ These numbers are used by **both** `_info_box` (laying rows out) and
# [EN] `legend_height()` (summing the height); they used to be literals in both places, so changing
# [EN] one inevitably drifted by 15px.
LEG_DY_TITLE, LEG_DY_WHEN, LEG_DY_DETAIL, LEG_DY_HEAD = 22.0, 18.0, 20.0, 17.0
LEG_ITEM_H = 15.0

#: 图例区左上角的原点。
# [EN] : the legend area's top-left origin.
LEG_X0, LEG_Y0 = 12.0, 12.0

#: 楼名带的高度（像素）：解算房间时把 `span` 顶部往下推这么多，
#   给「整座建筑的名字」留出一条带子；楼名写在带子里，不再压在房子立面上
#   （用户 2026-10-15：「楼（地点）名字在建筑立面」）。
#   ⚠ 与 `solve(name_band=…)` 配套；小地图不传（楼名写在框上沿）。
# [EN] Height of the building-name band (px): when solving, push the room-computing `span`'s top
# [EN] down by this much to reserve a strip for the building's name; the name goes in the strip
# [EN] instead of on the building facade (user 2026-10-15: "the building name is on the facade").
# [EN] Paired with `solve(name_band=…)`; the minimap does not pass it (its name sits on the frame edge).
NAME_BAND = 26.0

#: 门缺口的**最大宽度**（px）。2026-10-22 从 46 砍到 18（用户：「门现在画的太大 太难看了
#: 换一种小的不占用空间的画法」）。真实宽度还会按房宽再收一档（房宽的 24%），
#: 小房间的门不会撑满整面墙。
# [EN] : the **maximum width** of a door opening (px). Cut from 46 to 18 on 2026-10-22 (user: "the
# [EN] doors are drawn too big and too ugly; use a smaller style that doesn't take up space"). The
# [EN] actual width shrinks further with the room (24% of it) so a tiny room does not get a door that
# [EN] spans the whole wall.
DOOR_W_MAX = 18.0

#: 墙的**厚度**（两圈描边的偏移量）。`_draw_plan` 画双线用 `inset 0 / 3.5`、`stroke 1.7` ⇒
#: 实际占 `0.85 + 3.5 + 0.85 = 5.2px`。门缺口那条 paper 线必须比它宽，才开得干净。
# [EN] : the wall's **thickness** (the offset between the two strokes). `_draw_plan` uses inset 0 /
# [EN] 3.5 with stroke 1.7 => a real 0.85 + 3.5 + 0.85 = 5.2px. The door-opening paper line must be
# [EN] wider than this to cut the gap cleanly.
WALL_T = 5.2

#: 道路的宽度：外圈（路的边）与内芯（路面）。
#   与街道图同一套画法但细一档（`_draw_street` 用 9 / 6）—— 室内图上的"廊"比街道窄。
#   ⚠ 这两个数**必须大于网格线宽（0.5）一个数量级**，否则又会变成"看不清的注解"，
#     而那正是用户 2026-10-22 报的那件事（旧版是 2.0 宽的虚线）。
# [EN] Road widths: the outer edge and the inner surface. Same convention as the street map but one
# [EN] tier thinner (that one uses 9 / 6) -- a corridor indoors is narrower than a street.
# [EN] ⚠ Both must be **an order of magnitude wider than the grid stroke (0.5)**, or it becomes
# [EN] "an unreadable annotation" again -- exactly what the user reported on 2026-10-22 (the old
# [EN] version was a 2.0-wide dashed line).



def legend_items(detail: str) -> list[tuple[str, str]]:
    """这张图该配哪几条图例（**记号 → 说明**）。

    ★ 图例**跟着细致程度走**：室内图不该出现"桥"的图例（那是街道图才有的），
      街道图也不该写"房间墙"。写上一堆这张图上根本没有的记号，
      比不写图例更糟 —— 看的人会去图上找那个不存在的东西。
    [EN] Which legend entries this map should carry (**symbol -> description**).
    [EN] ★ The legend **follows the level of detail**: an indoor map should not list "bridge" (that
    [EN] belongs to a street map), and a street map should not say "room wall". Listing a pile of
    [EN] symbols that are not on the map at all is worse than no legend -- the viewer goes looking for
    [EN] something that isn't there.
    """
    if detail in (MM.DETAIL_IN, MM.DETAIL_IN_OUT):
        # ★★★ 2026-10-22（用户：「**大地图里的两条虚线有什么用处？**」）：
        #   那两条虚线是 `_draw_plan` 画的**通路**（`layout.links`：堂屋→后厨、堂屋→柜台
        #   这类"从这里走到那里"的廊/甬道，见 ③ 那一段）。图例里**一直没有它** ——
        #   于是图上有虚线、图上找不到解释，这是**图例的缺口**，不是用户看不懂。
        #   现在补一条，并且照实画成**虚线**（不是画成实线的「街道」，那是整体图才有的）。
        # [EN] ★★★ 2026-10-22 (user: "**what are the two dashed lines in the big map for?**"):
        # [EN] they are the **paths** drawn by `_draw_plan` (`layout.links`: hall->kitchen,
        # [EN] hall->counter -- the corridors connecting "from here to there", see section ③).
        # [EN] The legend **never listed them**, so the map had dashed lines and no explanation --
        # [EN] a **gap in the legend**, not the user failing to understand.
        # [EN] Now there is an entry, drawn as an actual **dashed** mark (not the solid "street" mark,
        # [EN] which belongs to the overview map).
        # ★★★ 2026-10-22：`('path', …)` 与 `has_links` **一起删掉了**。
        #   上一轮我给"通路"补了图例（因为用户问"这两条虚线有什么用"），
        #   这一轮用户要求「虚线去掉」⇒ 图上不再画，图例也就**不许再列**
        #   （"图例写着图上没有的记号"比不写更糟，这条纪律出自本函数说明）。
        # [EN] ★★★ 2026-10-22: `('path', ...)` and `has_links` were **removed together**. Last round I
        # [EN] added a legend entry for the paths (the user asked what the dashed lines were); this
        # [EN] round the user asked to "remove the dashed lines", so they are no longer drawn and the
        # [EN] legend **must not list them** ("naming marks the map does not carry" is worse than none).
        # ★★★ 2026-10-26：`('road', …)` **删掉** —— 室内图不再画路，图例也就不许再列
        #   （本函数的纪律："图例写着图上没有的记号比不写更糟"）。
        #   室内图表达"房间怎么走"靠 `door` 那一条（门开在共用墙上），那是建筑制图的正确记号。
        # [EN] ★★★ 2026-10-26: `('road', ...)` **removed** -- the indoor plan no longer draws roads,
        # [EN] so the legend must not list them (this function's own rule: "naming marks the map does
        # [EN] not carry is worse than none"). Indoors, "how rooms connect" is the `door` entry
        # [EN] (openings in a shared wall), which is the correct drafting convention.
        items = [('wall', t('房间墙')), ('door', t('门（缺口 + 门扇）'))]
        items += [('furn', t('屋内陈设')), ('frame', t('整座建筑'))]
        if detail == MM.DETAIL_IN_OUT:
            items.append(('ground', t('院子（露天）')))
        return items
    if detail == MM.DETAIL_WHOLE:
        # ★★★ 2026-10-27：这两档（`整体` / `局部`）**返回空**。
        #
        #   它们原来列的是「建筑 / 街道 / 水系 / 小建筑（缩略）」—— 那是**老街道图**
        #   （`_draw_street`）的记号表。而现在这两档都走城市图/城际图/甲板图，
        #   各自在**右下角**有自己的图例（`_city_legend` / `_region_legend` /
        #   `_deck_legend`）。在左边再列一套的后果是：
        #     · **两套图例互相矛盾**：左边说"街道"、右下说"次干道"，读者不知道信哪个；
        #     · 左边列的"建筑 / 小建筑"在导览图上并不存在（现在画的是分类符号）。
        #   ⇒ 返回空表 ⇒ `legend_height()` 自动跟着变小 ⇒ 绘图区变大（两处自动一致）。
        #   ⚠ 这不是"删内容"，是**去掉一份会说错话的说明**。这也正是本函数自己的纪律：
        #     "图例写着图上没有的记号，比不写更糟"。
        # [EN] ★★★ 2026-10-27: these two tiers (`整体` / `局部`) **return an empty list**. They used
        # [EN] to list "building / street / water / thumbnail building" -- the mark table of the **old
        # [EN] street map** (`_draw_street`). Both tiers now go to the city / region / deck renderers,
        # [EN] each with its own legend in the **bottom-right** (`_city_legend` / `_region_legend` /
        # [EN] `_deck_legend`). A second set on the left means (a) **two contradicting legends** (left
        # [EN] says "street", bottom-right says "secondary road") and (b) entries that do not exist on a
        # [EN] guide map ("building / thumbnail building" when classified symbols are drawn). => Return
        # [EN] empty, so `legend_height()` shrinks and the drawing area grows -- both stay consistent
        # [EN] automatically. ⚠ Not "removing content" but **removing a caption that would be wrong**,
        # [EN] which is this function's own rule: "naming marks the map does not carry is worse".
        return []
    return []


def build_detail_shapes(layout: Layout | None, *, width: int = W, height: int = H,
                        current: str = '', detail: str = '',
                        place: str = '', when: str = '',
                        palette: dict | None = None,
                        font: str | None = None,
                        style=None) -> list:
    """把一份布局画成**大地图**的形状列表。

    Args:
        layout:  `map_layout.Layout`（与小地图**同一份数据**）。
        width/height: 画布尺寸（默认 940×600）。
        current: 现在人在哪一间（垫朱砂）。
        detail:  细致程度；**空则由 `minimap.detail_of()` 自己判**
                 （与画小地图用的是同一个函数 —— 两处档位必须一致）。
        place:   信息框里的**地点**（通常是整座建筑或这一处的名字）。
        when:    信息框里的**时间**（"第 3 天 · 戌时"这种，调用方组装）。

    返回的形状直接交给 `fcv.Canvas(shapes=…)`。**纯函数** —— 同一份输入
    永远画出同一张图（这是"存本地、以后复用"成立的前提）。
    
    [EN] Draw a layout into the **big map**'s shape list.
        Args:
            layout:  `map_layout.Layout` (**the same data** as the minimap).
            width/height: canvas size (default 940x600).
            current: which room the character is in now (gets a cinnabar wash).
            detail:  level of detail; **empty means `minimap.detail_of()` decides**
                     (the same function as the minimap uses -- the two tiers must agree).
            place:   the **location** in the info box (usually the whole building or this spot).
            when:    the **time** in the info box (something like "day 3 · the hour of the dog",
                     assembled by the caller).
            style:   the building tradition (`worldstyle.Style`). **Empty means "detect it"**
                     (`worldstyle.for_layout`): a program's recorded profile first, then the place
                     names and notes. ★ It decides three things that used to be hard-coded: how the
                     city blocks are cut, what the region map emphasises, and whether a ship is
                     drawn as a hull rather than as a courtyard house.
        The returned shapes go straight to `fcv.Canvas(shapes=…)`. **A pure function** -- one input
        always draws one map (that is what makes "save locally, reuse later" valid).
    """
    pal = dict(PALETTE)
    pal.update(palette or {})
    Wd, Hd = int(width), int(height)
    detail = detail or MM.detail_of(layout)
    shapes: list = []
    shapes.append(fcv.Rect(0, 0, Wd, Hd,
                           paint=ft.Paint(color=pal['paper'],
                                          style=ft.PaintingStyle.FILL)))
    # ★ 绘图区**先算**（2026-10-22）：底纹要收进它里面，不能再铺满画布
    #   （铺满时会有线正好穿过比例尺的刻度字，见 `_grid` 的说明）。
    # [EN] The drawing area is computed **first** (2026-10-22): the underlay must stay inside it and
    # [EN] no longer cover the canvas (a full-canvas grid struck through the scale graduations; see
    # [EN] `_grid`).
    ox0, oy0, cw0, ch0 = layout_area(Wd, Hd, detail)
    _grid(shapes, Wd, Hd, pal, box=(ox0, oy0, cw0, ch0))

    places = list((layout.places if layout else []) or [])
    if not places:
        # ★★ 2026-10-26：**有任务书就不许提前返回**。
        #
        #   这一段原来只认 `places`（一地点一点的老数据），于是"只有任务书、没有点表"的
        #   新路径会在这里**直接画出「（还没有地点设定）」并 return** ——
        #   表现是"新解算一行都没跑到"，而代码看着哪都对（实测踩到：两种输入画出
        #   一模一样的 75 个图元，正是因为它根本没往下走）。
        #   任务书本身就够解出整张图 ⇒ 有空点表时继续往下走。
        # [EN] ★★ 2026-10-26: **never return early when a program exists.** This block only looked
        # [EN] at `places` (the old one-point-per-place data), so the new path ("program only, no
        # [EN] point table") drew "（还没有地点设定）" here and returned -- i.e. **not one line of the new
        # [EN] solver ran**, while the code looked correct everywhere (measured: both inputs produced
        # [EN] the same 75 shapes precisely because it never went further).
        _has_prog = bool(getattr(layout, 'program', None)) if layout is not None else False
        if not _has_prog:
            shapes.append(MM._text(Wd / 2, Hd / 2 - 8, t('（还没有地点设定）'), size=15,
                                   color=pal['muted'], font=font, center=True))
            _info_box(shapes, pal, layout, detail, place=place, when=when, font=font)
            return shapes

    # 绘图区：**给左边的图例区让出位置**（图例压在图上会挡住内容）
    # ★ 2026-10-12：让位的宽度/高度**算出来**（`legend_height()`），不再靠写死的方框 ——
    #   图例条目数跟着细致程度变（3~5 条），写死就会溢出（用户看到的"字在方框外面"）。
    # [EN] Drawing area: **leave room for the legend area on the left** (a legend pressed onto the map
    # [EN] hides the content).
    # [EN] ★ 2026-10-12: the space given way is **computed** (`legend_height()`), no longer a hardcoded
    # [EN] box -- the number of legend entries follows the level of detail (3~5), and hardcoding made
    # [EN] it overflow (the "text outside the box" the user saw).
    ox, oy, cw, ch = layout_area(Wd, Hd, detail)
    # ★★ 绘图区是**给 `plan_audit.solve()` 的那块 `span`** ——
    #   解算与绘制共用同一个范围，两边的几何才不会漂（这是 `plan_audit` 存在的理由）。
    # [EN] ★★ The drawing area **is the `span` handed to `plan_audit.solve()`** -- solving and drawing
    # [EN] share one extent so the two geometries cannot drift (the reason `plan_audit` exists).
    span = layout_span(Wd, Hd, detail)

    def px(p: Place) -> tuple:
        """归一化 → 像素（**全图唯一的一份换算**，解算与绘制共用）。
        [EN] Normalised -> pixels (**the one mapping in this image**, shared by solving and
        [EN] drawing)."""
        return (ox + 14 + p.x * (cw - 28), oy + 14 + p.y * (ch - 28))

    # ★★★ 2026-10-26：**优先用"房间任务书"解算出来的平面**（`image_gen/roomplan.py`）。
    #
    #   为什么：老的 `PA.solve()` 是从"一堆点"反推房间（气泡图 + 互相推开），
    #   于是必然出现用户报的那几件事：叠、房间不拼满、门悬在房子外面、二楼在同一层。
    #   新的解算从"哪些房间/谁挨着谁/几层"直接切出**拼满外轮廓**的平面（纯函数、可复现）。
    #
    #   接入方式刻意做得很薄：解算结果包成同一个 `PA.Plan` 形状
    #   （`roomplan.to_plan`），所以下面 `_draw_plan` **一行都不用改**。
    #   ⚠ 拿不到任务书（老缓存 / 没设置 / 解算失败）⇒ **原样走老路**。
    #     两条路都要能走：新解算是"更好"，不是"必需"。
    # [EN] ★★★ 2026-10-26: **prefer the plan solved from the room program**
    # [EN] (`image_gen/roomplan.py`). The old `PA.solve()` infers rooms from a pile of points (bubble
    # [EN] diagram + push apart), which necessarily produces exactly what the user reported:
    # [EN] overlap, rooms not tiling, doors floating outside, floor 2 on the same plan. The new solver
    # [EN] slices a tiling plan straight from "which rooms / who touches whom / how many floors"
    # [EN] (pure function, reproducible). The wiring is deliberately thin: the result is wrapped into
    # [EN] the same `PA.Plan` shape (`roomplan.to_plan`), so `_draw_plan` below needs no change.
    # [EN] ⚠ No program (old cache / not set / solve failed) => **the old path runs unchanged**.
    plan = None
    # ⚠ 几何**每次渲染时现解**，不从缓存里读坐标 —— 这正是延续性的来源：
    #   缓存里存的是**任务书**（文本），解算确定性 ⇒ 同一任务书永远同一张图；
    #   而"存坐标"则会像旧 `锚定.json` 那样把错的布局永久固化。
    # [EN] ⚠ Geometry is **solved at render time**, never read back from cache -- that is where
    # [EN] continuity comes from: the cache stores the **program** (text) and solving is
    # [EN] deterministic, so one program always yields one plan. Storing coordinates instead is what
    # [EN] fossilised the wrong layout in the old `锚定.json`.
    try:
        _pd = getattr(layout, 'program', None) if layout is not None else None
        _prog = RP.Program.from_dict(_pd) if _pd else None
        if _prog is not None:
            _fps = RP.solve(_prog, span=span)
            if _fps:
                # 选哪一层：`current` 在哪层就画哪层；否则一层。
                _fl = next((f for f, fp in _fps.items()
                            if current and current in fp.rooms), 1)
                _fp = _fps.get(_fl) or _fps[min(_fps)]
                plan = RP.to_plan(_fp, detail=detail, current=current, place=place)
    except Exception:                                         # noqa: BLE001
        plan = None
    if plan is None:
        plan = PA.solve(layout, px=px, span=span, detail=detail, current=current,
                        grow=PLAN_GROW, name_band=NAME_BAND)

    # ── 分派：四种**尺度**各用各的画法（2026-10-26）───────────────────    # 原来只有两条路：`整体` → `_draw_street`（街道图），其余 → `_draw_plan`（室内）。
    # 于是**城际图被画成了城市街道图** —— 两座隔着几百里的城，被画成两个相邻小方块加一条线，
    # 读者读不出"远"，也读不出"这一带是山地还是平原"。
    #
    # 现在按 `scale.scale_of()` 判四路：
    #   room   → `_draw_plan`（墙/门/陈设，已有）
    #   city   → `scalemap.build_city_shapes`（街区＋分级路网＋POI，类高德）
    #   region → `scalemap.build_region_shapes`（政区＋城镇等级＋官道＋山河，类标准地图）
    #   deck   → `scalemap.build_deck_shapes`（船体＋舱段，舟船专用；2026-10-26 加）
    #
    # ⚠ **有任务书就一定走室内**：任务书本身就是"这栋房子里面长什么样"，
    #   它的名字可能一个都不认识（外文/生僻），那时 `scale_of` 会兜底成 city ——
    #   结果是"我明明有平面图，却给我画了张城市图"。所以 program 优先。
    # ⚠ 新渲染器**抛异常就退回 `_draw_street`**：宁可画一张简陋的街道图，
    #   也不要整张图空白（空白是最坏的结果，用户会以为程序坏了）。
    #
    # ★★★ 2026-10-26（第二刀）：这一层原来**从来不知道这是什么世界**。城市图/城际图
    #   一辈子用同一套默认值画（街区永远 Voronoi、城际永远地形为主、船永远像四合院）。
    #   现在先判一次风格（`worldstyle.for_layout`：任务书里记的优先，其次看地名/备注），
    #   再把它交给三个渲染器与三份图例 —— **判一次，全层共用**，不许各自再猜一遍。
    # [EN] Dispatch by **scale** (2026-10-26), now four ways. There used to be two paths:
    # [EN] `整体` -> `_draw_street` and everything else -> `_draw_plan`, so an **inter-city map was
    # [EN] drawn as a town street map**. Now: room -> `_draw_plan`; city -> `build_city_shapes`;
    # [EN] region -> `build_region_shapes`; deck -> `build_deck_shapes` (ships, added 2026-10-26).
    # [EN] ⚠ **A program always means indoors**: the program *is* "inside this building", and its
    # [EN] names may all be unrecognised (foreign/rare), in which case `scale_of` falls back to city
    # [EN] -- i.e. "I have a floor plan but you drew me a city map". So program wins.
    # [EN] ⚠ If a renderer raises, **fall back to `_draw_street`**: a crude street map beats a blank
    # [EN] canvas. ★★★ 2026-10-26 (second cut): this layer **never knew what world it was in**. The
    # [EN] city and region maps used one set of defaults forever (Voronoi blocks, terrain-led region,
    # [EN] and a ship that looked like a courtyard house). Now the tradition is judged once
    # [EN] (`worldstyle.for_layout`: the program's record first, then names and notes) and handed to
    # [EN] all three renderers and all three legends -- **judged once, shared by the layer**, never
    # [EN] re-guessed per function.
    _style = style
    if _style is None:
        try:
            _style = WS.for_layout(layout, places).style
        except Exception:                                     # noqa: BLE001
            _style = None
    _scale = SC.ROOM
    try:
        _kind = str(getattr(layout, 'kind', '') or '')
        _pd = getattr(layout, 'program', None) if layout is not None else None
        _prog = RP.Program.from_dict(_pd) if _pd else None
        # ★★★ 2026-10-27（用户报的真 bug）：**`kind` 是尺度声明，任务书不能推翻它**。
        #
        #   原来这里是 `ROOM if program else scale_of(layout)` —— 那条规则成立的前提是
        #   "只有室内图才有任务书"。**这个前提已经不成立了**：`day_layout` 现在给每一档
        #   都推一份任务书（`整体` 也推）。于是一份 6 个地点的街区版任务书被当成一栋房子，
        #   `roomplan` 把「石桥 / 渡口 / 兰若寺」切成横条房间：
        #     · 大地图 = 一摞方框挤在右下角（"多层方框合起来"）；
        #     · 小地图 = 另一套画法（不规则多边形）；
        #     · 用户看到的："地图在右下角，都出了对话框边界"。
        #   ⇒ 现在的判法（三层，按可解释性排序）：
        #     ① `kind='室内'` ⇒ **一律室内**。作者/模型已经声明了"这是一栋房子的里面"，
        #        而且室内图的名字常是外文/生僻，`scale_of` 会误判成 city（这条担忧是真的，
        #        但它只在"声明了室内"时才需要保护）。
        #     ② `kind='整体'` ⇒ **一律按 `scale_of`**。'整体' 的定义就是"地点之间的方位与
        #        通路"（`world/atlas.py`），它根本不是一栋房子，任务书在这里只描述"有哪些处"。
        #     ③ `kind='局部'` 或**空**（老缓存）⇒ 看**任务书是不是一栋房子**
        #        （`roomplan.is_one_building`：建筑名非空，或没有 ≥2 处"不是房间"的空间）。
        #        '局部' 的语义本来就含"房屋附近 / 房屋内部"两种，只能看内容分。
        # [EN] ★★★ 2026-10-27 (a real bug the user reported): **`kind` is the scale declaration and
        # [EN] a program must not overrule it.** The old rule was `ROOM if program else
        # [EN] scale_of(layout)`, whose premise was "only indoor maps carry a program". **That premise
        # [EN] is gone**: `day_layout` now derives a program for every tier, including `整体`. So a
        # [EN] street-level program with six places was treated as one house and `roomplan` cut
        # [EN] 石桥 / 渡口 / 兰若寺 into strip-shaped rooms -- the big map became "a stack of boxes
        # [EN] squeezed into the bottom-right", the minimap drew something else, and the user reported
        # [EN] "the map sits in the bottom-right corner, outside the dialog". => Three-tier rule:
        # [EN] (1) `kind='室内'` => always indoors (the tier is declared, and indoor names are often
        # [EN] foreign and would be misjudged as city -- a real concern, but only when indoors is
        # [EN] declared); (2) `kind='整体'` => always `scale_of` ('overall' means "bearings and paths
        # [EN] between places", never one house; the program only says which places exist);
        # [EN] (3) `kind='局部'` or empty (old cache) => ask whether the program is **one building**
        # [EN] (`roomplan.is_one_building`: a named building, or fewer than two non-room spaces),
        # [EN] because 'local' legitimately means either "near the house" or "inside the house".
        if _kind == '室内':
            _scale = SC.ROOM
        elif _kind == '整体':
            _scale = SC.scale_of(layout, style=_style)
        elif _prog is not None and RP.is_one_building(_prog):
            _scale = SC.ROOM
        else:
            _scale = SC.scale_of(layout, style=_style)
    except Exception:                                         # noqa: BLE001
        _scale = SC.ROOM
    # ★★★ 2026-10-27（用户："现有地图重新绘制"时量出来的第二个缺陷）：
    #   城市图/城际图的取景原来是"整个绘图区 = 归一化 0~1"，默认**地点铺满全图**。
    #   而真实数据里坐标常挤在中间一小块 —— 实测那份当天地图的 6 处地点只用了绘图区的
    #   **34% × 37%**，画出来是"中间一坨、四周一大片空街区"。用户觉得"地图不对"，
    #   很大一部分是**这个**：图上 2/3 的面积不携带任何信息。
    #   ⇒ 城市/城际用**紧凑取景**（`scale.frame_px`：地点实际所占 + 12% 边距），
    #     室内与甲板**不动** —— 它们的几何由解算器按外轮廓铺满，本来就该吃满绘图区。
    #   ★ 这不是编坐标：坐标原样不动，改的是"看多大一片"（缩放地图本来就是这件事）。
    # [EN] ★★★ 2026-10-27 (the second defect measured while re-drawing the live maps): the city and
    # [EN] region framing used to be "the whole drawing area = normalised 0..1", i.e. it assumed the
    # [EN] places fill the picture. Real coordinates often huddle in the middle -- measured, the six
    # [EN] places of that day's map used only **34% x 37%** of the drawing area, so the picture was "a
    # [EN] blob in the middle and a large empty block field around it". Much of the user's "this looks
    # [EN] wrong" is exactly this: two thirds of the area carries no information. => The city/region
    # [EN] tiers now use **tight framing** (`scale.frame_px`: the places' real extent plus a 12% margin);
    # [EN] the room and deck tiers are **untouched** -- their geometry fills the envelope by the solver
    # [EN] and should fill the drawing area. ★ Not fabrication: coordinates are untouched; what changes
    # [EN] is how much ground is framed, which is what zooming a map means.
    _px_tight = px
    try:
        if _scale in (SC.CITY, SC.REGION) and places:
            # ★ 2026-10-27：`also=` 把水系/院墙也纳入取景 —— 只按地点取景会把
            #   "比地点更靠边"的海岸线整个推到框外（实测 y≈1079 / 画布 602）。
            # [EN] ★ 2026-10-27: `also=` brings water and walls into the framing -- framing by places
            # [EN] alone pushes a coastline that reaches further out entirely off-canvas (measured
            # [EN] y~1079 on a 602-tall canvas).
            _px_tight = SC.frame_px(
                places, (ox + 14, oy + 14, ox + cw - 14, oy + ch - 14),
                also=SC.layout_extra(layout))
    except Exception:                                         # noqa: BLE001
        _px_tight = px
    if _scale == SC.REGION:
        try:
            _info = SM.build_region_shapes(shapes, layout, places, _px_tight, pal=pal,
                                          font=font, span=span, current=current,
                                          style=_style)
            _region_legend(shapes, pal, _info, font=font, span=span, style=_style)
        except Exception:                                     # noqa: BLE001
            _draw_street(shapes, layout, places, _px_tight, pal, font=font, span=span)
    elif _scale == SC.CITY:
        try:
            _cinfo = SM.build_city_shapes(shapes, layout, places, _px_tight, pal=pal,
                                         font=font, span=span, current=current,
                                         style=_style)
            # ★★ 2026-10-26：城市图原来**根本没有图例**（只有城际图有）。
            #   而标准地图的"要素"里，图例是最基本的一项 —— 没有它，读者看到
            #   "一圈圈不同粗细的线、几个大小不一的圆点"，只能猜。
            # [EN] ★★ 2026-10-26: the city map had **no legend at all** (only the region map did).
            # [EN] A legend is among the most basic elements of a standard map -- without it the
            # [EN] reader sees "lines of assorted widths and dots of assorted sizes" and can only guess.
            _city_legend(shapes, pal, _cinfo, font=font, span=span)
        except Exception:                                     # noqa: BLE001
            _draw_street(shapes, layout, places, _px_tight, pal, font=font, span=span)
    elif _scale == SC.DECK:
        try:
            _dinfo = SM.build_deck_shapes(shapes, layout, places, px, pal=pal,
                                          font=font, span=span, current=current,
                                          style=_style)
            _deck_legend(shapes, pal, _dinfo, font=font, span=span)
        except Exception:                                     # noqa: BLE001
            _draw_street(shapes, layout, places, px, pal, font=font, span=span)
    else:
        _draw_plan(shapes, plan, layout, places, px, current=current,
                   pal=pal, font=font, span=span)

    _info_box(shapes, pal, layout, detail, place=place, when=when, font=font)
    _north(shapes, Wd, Hd, pal, font=font)
    return shapes


# ══════════════════════════════════════════════════════════════════
#  底纹：测绘纸的淡格（"这是一张地图"的第一眼信号）
# [EN] Underlay: the faint grid of surveying paper (the first-glance signal that "this is a map")
# ══════════════════════════════════════════════════════════════════
GRID = 24


def _grid(shapes: list, W: int, H: int, pal: dict,
          box: tuple | None = None) -> None:
    """测绘纸底纹（淡格）。

    ★★★ 2026-10-22（用户：「**大地图的比例尺被挡住了**」）：底纹**只许画在绘图区里**。
      以前它铺满整张画布（`range(GRID, W, GRID)` / `0..H`），于是：
        · 一条横线正好落在 `y = 576` —— **那是刻度字「0 1 2 3 4」所在的那一行**
          （`_scale_bar` 把刻度字画在 `y + h + 1`，而 y=566、h=9 ⇒ 576），
          数字被一根细线当头穿过；
        · 一串竖线从画布顶一直拉到画布底，穿过比例尺的标题与尺身，
          也穿过左上角的图例。
      比例尺虽然画得更晚（在底纹之上），但**字底下透出来的线**照样让人读不清，
      用户看到的就是"比例尺被挡住了"。⇒ 底纹收进 `box`（绘图区），
      图例、比例尺、指北针那一圈保持干净。

    `box` 缺省 = 整张画布（老行为），只给"确实要整页底纹"的调用方用。

        English:
    The surveying-paper underlay (faint grid).
    ★★★ 2026-10-22 (user: "**the big map's scale bar is covered**"): the underlay may **only be
    drawn inside the drawing area**. It used to cover the whole canvas, so a horizontal line landed
    exactly on `y = 576` -- **the row the graduations "0 1 2 3 4" sit on** (the scale bar draws them
    at `y + h + 1` with y=566, h=9 => 576), striking through the numbers; and a run of vertical lines
    ran from the very top to the very bottom, crossing the scale bar's title, the bar itself, and the
    legend in the top-left. The scale bar is drawn later (on top of the grid), but **lines showing
    through behind the glyphs** still makes it unreadable -- exactly "the scale bar is covered".
    => The underlay is confined to `box` (the drawing area); the legend, the scale bar and the north
    arrow keep a clean surround. `box` defaults to the whole canvas (the old behaviour) for callers
    that genuinely want a full-page underlay.
    """
    paint = ft.Paint(color=pal['grid'], stroke_width=0.5,
                     style=ft.PaintingStyle.STROKE)
    if box is None:
        x0, y0, x1, y1 = 0.0, 0.0, float(W), float(H)
    else:
        x0, y0, x1, y1 = (float(box[0]), float(box[1]),
                          float(box[0]) + float(box[2]), float(box[1]) + float(box[3]))
    x = GRID * math.ceil(x0 / GRID)
    while x < x1:
        shapes.append(fcv.Line(x, y0, x, y1, paint=paint))
        x += GRID
    y = GRID * math.ceil(y0 / GRID)
    while y < y1:
        shapes.append(fcv.Line(x0, y, x1, y, paint=paint))
        y += GRID


# ══════════════════════════════════════════════════════════════════
#  ① 平面图（室内 / 室内外 / 局部）—— 标准装修图的画法
# [EN] ① Floor plan (indoor / indoor+outdoor / local) -- standard interior-drawing conventions
# ══════════════════════════════════════════════════════════════════
def _draw_plan(shapes: list, plan, layout, places: list, px, *,
               current: str, pal: dict, font: str | None,
               span: tuple) -> None:
    """平面图：**照着 `plan_audit.solve()` 的结果画**。

    ★★ 为什么要照解算结果画（2026-10-12）：以前这个函数**自己**算房间矩形、
      自己算院子 —— 于是"房间框"与"院子框"两套算法各画各的，必然出现重叠与
      "家具落在墙外"（用户看出来的那两个问题）。
      现在几何**只有 `plan_audit` 一份**（`solve()` 解算 + `audit()` 审核），
      这里只负责把解算出来的坐标画成形状 —— **画出来的必然与审核的一致**。

    ★ 标签全部**贴墙**（用户：「建筑的名字标记都放到墙的旁边 不要放到别的东西的上面」）：
      · 房间名 → 贴那间房的**上墙内侧**；
      · 建筑名 → 贴**房子外框的上墙**（垫一块纸色，免得被墙线穿过）；
      · 院子名 → 贴院墙上沿内侧；
      · 符号（井 / 树）→ 名字贴**符号右侧**，不压在符号上。
    [EN] Floor plan: **drawn from `plan_audit.solve()`'s result**.
    [EN] ★★ Why draw from the solved result (2026-10-12): this function used to compute the room
    [EN] rectangles and the courtyard **itself** -- two separate algorithms drawing independently, so
    [EN] overlap and "furniture outside the wall" (the two problems the user spotted) were inevitable.
    [EN] Now the geometry has **one implementation only** (`plan_audit`: `solve()` solves, `audit()`
    [EN] audits) and this only turns the solved coordinates into shapes -- **what is drawn necessarily
    [EN] matches what was audited**.
    [EN] ★ All labels **hug the wall** (the user: "put the building's name label beside the wall, not
    [EN] on top of other things"):
    [EN] · room name -> the **inside of that room's top wall**;
    [EN] · building name -> the **top wall of the house frame** (on a paper-coloured patch so the wall
    [EN]   line does not run through it);
    [EN] · courtyard name -> inside the courtyard wall's top edge;
    [EN] · symbols (well / tree) -> the name goes **to the right of the symbol**, not on top of it.
    """
    # ── ① 院子：照解算结果画（**已经与房子互斥**）──
    # [EN] -- (1) Courtyard: drawn from the solved result (**already disjoint from the house**) --
    if plan.yard is not None:
        yx0, yy0, yx1, yy1 = plan.yard
        if yx1 - yx0 > 40 and yy1 - yy0 > 40:
            shapes.append(fcv.Rect(yx0, yy0, yx1 - yx0, yy1 - yy0,
                                   paint=ft.Paint(color=pal['ground'],
                                                  style=ft.PaintingStyle.FILL)))
            _stipple(shapes, yx0, yy0, yx1, yy1, pal)
            for gap in (0.0, 4.0):
                shapes.append(fcv.Rect(yx0 - gap, yy0 - gap,
                                       (yx1 - yx0) + 2 * gap, (yy1 - yy0) + 2 * gap,
                                       border_radius=2.0,
                                       paint=ft.Paint(color=pal['wall_hi'],
                                                      stroke_width=1.6,
                                                      style=ft.PaintingStyle.STROKE)))
            # 院子名**贴院墙上沿内侧**（不压在院里的东西上）
            # [EN] The courtyard name **hugs the inside of the courtyard wall's top edge** (it does
            # [EN] not press onto things in the yard)
            # ★ 2026-10-27（查"文字两两重叠"时抓到的）：院子在平面**最上面**时，
            #   院墙上沿与房子外框上沿**是同一条线** ⇒ 院子名与楼名写在同一个位置，
            #   两行字叠成一团（实测 院子（露天）(316,271) 与 临河楼(318,278) 相距 7px）。
            #   ⇒ 院名往下让 `_yard_label_dy`：与楼名同带时下移一个字高。
            # [EN] ★ 2026-10-27 (caught while checking text-vs-text overlap): when the courtyard sits at
            # [EN] the very top of the plan, its wall top edge **is** the house frame's top edge, so the
            # [EN] courtyard name and the building name are written at the same spot (measured: 7px
            # [EN] apart, i.e. two lines of glyphs on top of each other). => Drop the courtyard label by
            # [EN] one line height when it shares the band.
            MM._on_wall(shapes, yx0 + 8, yy0 + _yard_label_dy(plan, yy0, span), yy1 - yy0,
                        t('院子（露天）'), pal=pal,
                        color=pal['muted'], font=font, size=12)

    # ── ② 水系：波纹记号 ──
    # [EN] -- (2) Water system: ripple marks --
    if len(getattr(layout, 'water', None) or []) >= 2:
        # 水系的坐标是**归一化**的，与地点共用同一套换算（`px`）
        # [EN] Water coordinates are **normalised**, sharing the same mapping as locations (`px`)
        pts = [px(Place('', x=a, y=b)) for a, b in layout.water]
        els = [fcv.Path.MoveTo(pts[0][0], pts[0][1])]
        els += [fcv.Path.LineTo(x, y) for x, y in pts[1:]]
        shapes.append(fcv.Path(els, paint=ft.Paint(
            color=pal['water'], stroke_width=7.0, stroke_cap=ft.StrokeCap.ROUND,
            style=ft.PaintingStyle.STROKE)))
        for x, y in pts[::2]:
            shapes.append(fcv.Line(x - 6, y - 3, x - 6, y + 3,
                                   paint=ft.Paint(color=pal['paper'], stroke_width=1.4,
                                                  style=ft.PaintingStyle.STROKE)))

    # ── ③ 道路：**室内图不画路** ──
    # [EN] -- (3) Roads: **an indoor plan draws no roads** --
    #
    # ★★★ 2026-10-26（用户）：「地图中 如果是室内图 把路去掉
    #   如果是室外地图 按照标准地图画法绘制道路等所有元素」
    #
    #   这不是"回退"，是**语义纠正**。看一下这处的历史：
    #     · 2026-10-22 之前：画**虚线**（stroke 2.0 + dash），用户问「这两条虚线有什么用处？」
    #     · 2026-10-22：我把它改成**双线实心路带**（外 7 / 内 4.2），
    #       理由是"他要的是路，只是虚线太细太像标注"。
    #       那个判断**当时就不够准**：用户说"看不清"，我理解成"要画得更像路"，
    #       而他要的可能是"**这东西根本不该在这儿**"。
    #     · 2026-10-26：明确说了 —— 室内图**不该有路**。
    #
    #   ★ 为什么"室内画路"从原理上就是错的（不只是不好看）：
    #     平面图（floor plan）表达的是**墙以内的空间关系**；道路是**室外**的通行设施。
    #     把 `layout.links`（"堂屋→后厨"这种地点间通路）画进室内平面，
    #     等于把"城市尺度上两栋建筑之间怎么走"画到"一栋建筑内部怎么走"的图上 ——
    #     **尺度错位**。而且它按 `places` 的归一化坐标连，与房间矩形本来就对不齐，
    #     全靠"墙后画、盖住穿墙段"来救，那是在掩盖一个不该存在的图元。
    #   ★ 室内图表达"房间之间怎么走"用的是**门**（`plan.doors`：开在共用墙上的门洞），
    #     那才是建筑制图的正确记号。
    #
    #   ⚠ `layout.links` 本身**不删**：室外图（城市/城际）要靠它画路网，
    #     而 `world.spatial.route` 也用它算"怎么走"。只是**室内图不读它**。
    #
    # [EN] ★★★ 2026-10-26 (the user): "In the map: if it is an indoor plan, remove the roads; if it
    # [EN] is an outdoor map, draw roads and all other elements following standard cartographic
    # [EN] conventions." This is a **semantic correction**, not a rollback. History: before
    # [EN] 2026-10-22 it drew **dashed** lines and the user asked what those two dashed lines were; on
    # [EN] 2026-10-22 I changed them to **solid double-line road bands** (outer 7 / inner 4.2)
    # [EN] reasoning "he wants roads, the dashes are just too thin". That reading was **not accurate
    # [EN] enough**: he said "I cannot read it" and I heard "draw it more like a road", when he may
    # [EN] have meant "**this does not belong here at all**". On 2026-10-26 he said it plainly: an
    # [EN] indoor plan has no roads. ★ Why drawing roads indoors is wrong *in principle*, not just
    # [EN] ugly: a floor plan expresses **space relations inside the walls**, while roads are an
    # [EN] **outdoor** circulation facility. Drawing `layout.links` (place-to-place paths such as
    # [EN] hall->kitchen) onto an indoor plan puts "how to walk between two buildings at city scale"
    # [EN] onto "how to walk inside one building" -- a **scale mismatch**. They also connect
    # [EN] normalised `places` coordinates, so they never aligned with the room rectangles and only
    # [EN] looked acceptable because walls were drawn later and covered the crossings -- covering up a
    # [EN] primitive that should not exist. ★ Indoors, "how rooms connect" is expressed by **doors**
    # [EN] (`plan.doors`: openings in a shared wall), which is the correct drafting convention.
    # [EN] ⚠ `layout.links` is **not** deleted: outdoor maps need it for their road network, and
    # [EN] `world.spatial.route` uses it to compute routes. The **indoor plan simply does not read it**.

    # ── ④ 房间墙 + 门洞（照解算出来的矩形）──
    # [EN] -- (4) Room walls + door openings (from the solved rectangles) --
    for name, room in plan.rooms.items():
        x0, y0, x1, y1 = room.box
        if room.here:
            shapes.append(fcv.Rect(x0, y0, x1 - x0, y1 - y0, border_radius=2.0,
                                   paint=ft.Paint(color=pal['here'],
                                                  style=ft.PaintingStyle.FILL)))
        # 墙：**双线**（两圈描边 = 厚度）
        # [EN] Walls: **double line** (two rings of stroke = thickness)
        for inset in (0.0, 3.5):
            shapes.append(fcv.Rect(x0 + inset, y0 + inset,
                                   (x1 - x0) - 2 * inset, (y1 - y0) - 2 * inset,
                                   border_radius=1.5,
                                   paint=ft.Paint(color=pal['wall_hi'],
                                                  stroke_width=1.7,
                                                  style=ft.PaintingStyle.STROKE)))
        # 门：**缺口 + 一条门扇线**（2026-10-22 改）
        # [EN] Door: **opening + one leaf line** (changed 2026-10-22)
        #
        # ★★★ 用户 2026-10-22：「门现在画的太大 太难看了 换一种小的不占用空间的画法」。
        #   量出来的事实（改之前）：`dw = min(46, 房宽*0.42)`，而开合弧是
        #   `Arc(dx0, y1-dw, dw, dw*2)` ⇒ 外接 **46 × 92**，一个门就吃掉 4232 px²
        #   （画布的 0.75%），两个门 1.5%。在一个 940×600 的图上，那半个大扇形
        #   比旁边的家具还显眼，而且**弧会扫过房间中间** —— 那正是"难看"与"占地方"。
        #
        #   换成：缺口（宽度砍到 18px）+ **一条短门扇线**（垂直于墙、朝房间内、
        #   长度 = 缺口宽）。占 18 × 18 ≈ 324 px²，**只有原来的 8%**，
        #   而且完全贴着墙根，不侵入房间中间那块（家具、房间名都在那儿）。
        #
        #   ⚠ 缺口那条 paper 线**从 3.6 加到 6.2**：墙是双线（inset 0 / 3.5，各 stroke 1.7），
        #     实际厚度 0.85 + 3.5 + 0.85 = 5.2。3.6 盖不住 ⇒ 缺口内侧留着一道墙线，
        #     看着像"门框没开干净"（这也是"难看"的一部分）。现在中心也对齐到墙带中心。
        # [EN] ★★★ The user on 2026-10-22: "the doors are drawn too big and too ugly; use a smaller
        # [EN] style that doesn't take up space". Measured before the change: `dw = min(46, width*0.42)`
        # [EN] and the swing arc was `Arc(dx0, y1-dw, dw, dw*2)` => bounding box **46 x 92**, one door
        # [EN] eating 4232 px² (0.75% of the canvas), two doors 1.5%. On a 940x600 map that half fan
        # [EN] is louder than the furniture next to it, and the arc **sweeps through the middle of the
        # [EN] room** -- exactly what makes it ugly and space-hungry.
        # [EN] Replaced by: an opening (width cut to 18px) plus **one short leaf line**
        # [EN] (perpendicular to the wall, into the room, length = opening width). That is
        # [EN] 18 x 18 ≈ 324 px², **8% of the old area**, and it hugs the wall so it never intrudes on
        # [EN] the middle of the room (where furniture and the room name live).
        # [EN] ⚠ The paper line that opens the gap went **3.6 -> 6.2**: the wall is double-line
        # [EN] (inset 0 / 3.5, stroke 1.7 each) for a real thickness of 0.85 + 3.5 + 0.85 = 5.2, which
        # [EN] 3.6 could not cover -- leaving a wall line across the gap that read as "the doorway was
        # [EN] not cut cleanly" (part of "ugly"). Its centre now aligns with the wall band too.
        dw = min(DOOR_W_MAX, (x1 - x0) * 0.24)
        dx0 = (x0 + x1) / 2 - dw / 2
        # 缺口：覆盖整条墙带（宽 6.2，中心在墙带中心 y1-1.75）
        shapes.append(fcv.Line(dx0, y1 - 1.75, dx0 + dw, y1 - 1.75,
                               paint=ft.Paint(color=pal['paper'],
                                              stroke_width=WALL_T * 2 + 1.0,
                                              style=ft.PaintingStyle.STROKE)))
        # 门扇：从缺口左端垂直向**房间内**（y 变小），长度 = 缺口宽
        shapes.append(fcv.Line(dx0, y1, dx0, y1 - dw,
                               paint=ft.Paint(color=pal['wall_hi'], stroke_width=1.3,
                                              style=ft.PaintingStyle.STROKE)))
        # ★ 房间名**贴那间房的上墙内侧**（不再写在房间正中 —— 那里有家具与符号）
        # [EN] ★ The room name **hugs the inside of that room's top wall** (no longer dead centre --
        # [EN] furniture and symbols live there)
        MM._on_wall(shapes, (x0 + x1) / 2, y0 + 2, y1 - y0,
                 name if room.here else room.label, pal=pal,
                 color=pal['here'] if room.here else pal['ink'], font=font,
                 size=15, center=True)

    # ── ⑤ 建筑名：写在**房子外框上方的名字带**里（不再压在房子立面上）──
    #   `solve(name_band=NAME_BAND)` 已经把房子外框推到带子下方，所以楼名写在
    #   `span[1]` 一带（带子里）就恒在房子之上；`hy0` 是房子顶墙，楼名在其上方，
    #   与「名字压在立面上」彻底分开（用户 2026-10-15：「楼名字在建筑立面」）。
    # [EN] -- (5) The building name: in the **name band above the house frame** (no longer pressed on
    # [EN] the facade). `solve(name_band=NAME_BAND)` already pushed the house frame below the band, so
    # [EN] writing the name near `span[1]` (inside the band) always sits above the building; `hy0` is the
    # [EN] house's top wall, and the name is above it -- cleanly separated from "name on the facade"
    # [EN] (user 2026-10-15).
    if plan.house is not None:
        bname = _bldg_name(layout, places)
        if bname:
            hx0, hy0, hx1, hy1 = plan.house
            # 带子里的 y：`_on_wall` 会在 `y_wall + size + 1` 写字，这里取 `span[1]+4`，
            # 字落在带子中央、房子顶墙之上（带子高 = NAME_BAND，房子顶 ≥ span[1]+NAME_BAND+3）。
            # [EN] y in the band: `_on_wall` writes at `y_wall + size + 1`; `span[1] + 4` puts the text
            # [EN] in the band's middle, above the house top wall (band height = NAME_BAND, house top >=
            # [EN] span[1] + NAME_BAND + 3).
            MM._on_wall(shapes, hx0 + 10, span[1] + 4, hy1 - hy0, bname, pal=pal,
                     color=pal['ink'], font=font, size=15, bold=True)

    # ── ⑥ 陈设：照解算结果画（**已经在房间里**，这是「柜台跑到墙外」的修法）──
    # [EN] -- (6) Fixtures: drawn from the solved result (**already inside a room**, the fix for "the
    # [EN] counter outside the wall") --
    # ★ 家具名的避让清单：同一次绘制内共用（两件并排时名字不叠）。
    #   ⚠ **先塞进每个房间的名字带**：家具常常就贴在同一面墙上，而房间名也写在那条带里
    #     （`_on_wall(x0..x1, y0+2)`）。不预占的话，家具名会正好压在房间名上
    #     （实测：堂屋名与"柜台"只差 1px，肉眼就是一行糊字）。
    # [EN] Shared label-avoidance list for furniture names, **pre-seeded with each room's name band**:
    # [EN] furniture usually hugs the same wall the room name is written on (`_on_wall(x0..x1, y0+2)`).
    # [EN] Without pre-occupying it the furniture name lands on the room name (measured: 1px apart,
    # [EN] i.e. a smudged line of glyphs).
    _fix_taken: list = [(r.box[0] + 3.0, r.box[1] + 1.0, r.box[2] - 3.0, r.box[1] + 17.0)
                        for r in plan.rooms.values()]
    for name, (_owner, pos) in plan.fixtures.items():
        # 陈设在**当前那一间房**里 → 也标成"当前"（找柜台的戏就是在堂屋里）
        # [EN] A fixture in the **current room** is marked current too (a scene looking for the counter
        # [EN] is in the main hall)
        here = bool(plan.rooms.get(_owner) and plan.rooms[_owner].here)
        # ★ 2026-10-27：陈设的几何**有两条来源**，渲染层要都能接：
        #   ① 新解算器（`roomplan.solve`）：`plan.fixtures[name]` 是**中心点**，
        #      真实矩形在 `plan.fix_boxes[name]` —— 有它就用它（大小/朝向都来自它）；
        #   ② 老气路（`plan_audit`）：只有中心点，没有矩形 ⇒ 按**类型尺寸**造一个。
        #   ⚠ 不要在渲染层给死尺寸（比如 40×20）：那正是"家具全一样大"的来源。
        # [EN] ★ 2026-10-27: fixture geometry has **two sources** and the renderer must take both:
        # [EN] (1) the new solver (`roomplan.solve`) keeps a **centre point** in `plan.fixtures[name]`
        # [EN] and the real rectangle in `plan.fix_boxes[name]` -- use it when present (size and
        # [EN] orientation come from it); (2) the old bubble layout (`plan_audit`) has only the point,
        # [EN] so build a rectangle from the **class size**. ⚠ Never hard-code a size here (say 40x20):
        # [EN] that is exactly where "all furniture looks the same" came from.
        box = (getattr(plan, 'fix_boxes', None) or {}).get(name)
        if not box or len(box) != 4:
            _w, _h = FR.size_of(name)
            box = (pos[0] - _w / 2.0, pos[1] - _h / 2.0,
                   pos[0] + _w / 2.0, pos[1] + _h / 2.0)
        _furniture(shapes, tuple(box), pal, font, here, name,
                   room=(plan.rooms[_owner].box if _owner in plan.rooms else None),
                   taken=_fix_taken)

    # ── ⑦ 门 / 院子里的东西 / 其余地点 ──
    # [EN] -- (7) The gate / things in the yard / other locations --
    # 先收集这些"符号"的 bbox（供彼此避让），井 r=11、其余字形 scale=9
    # [EN] First gather these "symbols"' bboxes (for mutual avoidance): well r=11, else glyph scale=9
    sym_boxes: dict = {}
    for p in places:
        if p.name in plan.rooms or p.name in plan.fixtures:
            continue
        pt = plan.others.get(p.name)
        if pt is None:
            continue
        cx, cy = pt
        sr = 11.0 if ('井' in p.name or '泉' in p.name) else 9.0
        sym_boxes[p.name] = (cx - sr, cy - sr, cx + sr, cy + sr)
    for p in places:
        if p.name in plan.rooms or p.name in plan.fixtures:
            continue
        pt = plan.others.get(p.name)
        if pt is None:
            continue
        cx, cy = pt
        here = bool(current) and p.name == current
        if MM._is_gate(p.name):
            # 门是**边界**，在这张图上按门洞画（不写"门"字）
            # [EN] A gate is a **boundary**; drawn here as a door opening (no "门" character)
            shapes.append(fcv.Line(cx - 22, cy, cx + 22, cy,
                                   paint=ft.Paint(color=pal['wall_hi'], stroke_width=4.0,
                                                  stroke_cap=ft.StrokeCap.ROUND,
                                                  style=ft.PaintingStyle.STROKE)))
            _label(shapes, cx - 14, cy + 6, p.name, pal=pal, color=pal['muted'],
                   font=font, size=12, width=28)
            continue
        occ = [b for n, b in sym_boxes.items() if n != p.name]
        _symbol(shapes, cx, cy, p, pal, font, here, bounds=span, occupied=occ)


def _stipple(shapes: list, x0: float, y0: float, x1: float, y1: float,
             pal: dict) -> None:
    """院子铺细点（"这里是露天的地坪"，平面图的老记号）。
    [EN] Stipple the courtyard ("this is open ground", an old floor-plan convention)."""
    paint = ft.Paint(color=pal['wall'], stroke_width=1.0)
    step = 18.0
    y = y0 + step
    while y < y1 - 6:
        x = x0 + step * (0.6 if int(y / step) % 2 else 0.2)
        while x < x1 - 8:
            shapes.append(fcv.Circle(x, y, 0.9,
                                     paint=ft.Paint(color=pal['wall'],
                                                    style=ft.PaintingStyle.FILL)))
            x += step
        y += step
    _ = paint


def _label_fixture(shapes: list, box: tuple, name: str, pal: dict,
                   font: str | None, room: tuple | None,
                   taken: list | None = None, *, size: int = 10) -> None:
    """把家具名写在**不靠墙的那一侧**，并避开已写过的名字。

    ★ 为什么要有"避让"：两件家具并排贴在同一面墙上时（柜台 + 账台小柜），
      名字都在同一行、必然叠在一起 —— 叠起来的字比不写更难看。
      做法：按"候选位置"依次试（下方 → 上方 → 右侧），第一个不撞的用掉。
    ★ 为什么垫一块纸色：房间有朱砂底纹，字直接写上去会和底色搅在一起。
    [EN] Write the piece's name **on the side away from the wall**, avoiding names already written.
    ★ Why avoidance: two pieces side by side on the same wall put their names on one line and they
    [EN] overlap -- overlapping glyphs look worse than no label. Candidate slots are tried in order
    [EN] (below, above, right) and the first free one wins. ★ Why a paper patch: the room has a
    [EN] cinnabar wash and text straight on it muddles.
    """
    x0, y0, x1, y1 = (float(v) for v in box)
    tw = MM._cjk_w(str(name or ''), size)
    th = size + 3.0
    rx0, ry0, rx1, ry1 = (room if room else (x0 - 40, y0 - 40, x1 + 40, y1 + 40))
    cands: list[tuple[float, float]] = [
        ((x0 + x1) / 2.0 - tw / 2.0, y1 + 2.0),          # 下
        ((x0 + x1) / 2.0 - tw / 2.0, y0 - th - 1.0),     # 上
        (x1 + 3.0, (y0 + y1) / 2.0 - size * 0.55),        # 右
    ]
    # 贴墙的一侧要排除：如果这件家具贴着上墙，就把"上方"那个候选去掉
    # [EN] Drop the slot that faces the wall the piece hugs
    if room is not None:
        if y0 - ry0 < 14.0:
            cands.pop(1)
        elif ry1 - y1 < 14.0:
            cands.pop(0)
    # ★★★ 2026-10-27：名字要待在**室内**。
    #   房间框是**外轮廓**，墙是画在框**里面**的（向内 `furniture.WALL_IN`），
    #   所以贴着 `rx0 + 1` 写就正好**压在墙线上**（实测：靠角的小柜，名字被墙线穿过）。
    #   ⇒ 可写范围再往里退一个墙厚。
    # [EN] ★★★ 2026-10-27: the name must stay **indoors**. The room box is the **outer** outline
    # [EN] and the wall is drawn *inside* it (`furniture.WALL_IN`), so writing at `rx0 + 1` puts the
    # [EN] glyphs right on the wall line (measured: a cabinet in the corner, its name cut by the
    # [EN] wall). => The writable area retreats by one wall thickness.
    _inset = (FR.WALL_IN + 1.0) if room is not None else 0.0
    wx0, wy0 = rx0 + _inset, ry0 + _inset
    wx1, wy1 = rx1 - _inset, ry1 - _inset
    for lx, ly in cands:
        lx = min(max(lx, wx0), max(wx0, wx1 - tw - 1.0))
        ly = min(max(ly, wy0), max(wy0, wy1 - th))
        r = (lx - 1.0, ly - 1.0, lx + tw + 1.0, ly + th)
        if taken is not None and any(
                min(r[2], b[2]) - max(r[0], b[0]) > 0.5
                and min(r[3], b[3]) - max(r[1], b[1]) > 0.5 for b in taken):
            continue
        shapes.append(fcv.Rect(r[0], r[1], r[2] - r[0], r[3] - r[1],
                               paint=ft.Paint(color=pal.get('paper', '#f8f4ea'),
                                              style=ft.PaintingStyle.FILL)))
        shapes.append(MM._text(lx, ly, name, size=size,
                               color=pal.get('muted', '#8a9099'), font=font))
        if taken is not None:
            taken.append(r)
        return


def _furniture(shapes: list, box: tuple, pal: dict, font: str | None,
               here: bool, name: str, room: tuple | None = None,
               taken: list | None = None) -> None:
    """画一件陈设 —— **按类型**（柜台/床/灶/井/桌/柜/架/椅凳…各有记号）。

    ★★★ 2026-10-27（用户）：「室内图现在家具形状和摆放位置都不对 …
      家具的形状请参考一些现有标准画法绘制」。

    原来这里一律画 **40×20 的方块 + 斜线阴影**：
      · 柜台（长条）、井（圆的）、灶（两口锅）、床、桌、柜**全都长得一样**，
        谁也认不出哪件是什么；井甚至被画成方块（它在 `_symbol` 里本来是同心圆，
        只因为数据里井归成"陈设"就走到这条路上来了）；
      · 斜线是**剖面材料**的记号，不是家具 —— 一片房间铺满斜纹，反而什么都看不见。

    ⇒ 现在形状与尺寸都来自 `image_gen.furniture`（**唯一一份**表）：
      形状按建筑制图的家具图示（矩形 + 内部分隔/折角/锅眼/同心圆），
      尺寸按真实比例（柜台 48×16、床 38×54、井 直径 22…）。
      **画法与尺寸同源**，不会出现"摆放按 48 宽算、画出来 40 宽"的漂移。

    ★ 位置由 `roomplan._pack_fixtures` 给（那边知道墙与门在哪）；这里**只管长相**。
    [EN] Draw one fixture -- **by kind** (counter / bed / stove / well / table / cabinet / shelf /
    [EN] stool ... each with its own symbol). ★★★ 2026-10-27 (the user): "the indoor furniture shapes
    [EN] and positions are both wrong ... draw the shapes following existing standard conventions."
    [EN] This used to draw **one 40x20 block with hatch lines** for everything: a counter (a long
    [EN] band), a well (round), a stove (two pots), a bed, a table and a cabinet all looked alike, so
    [EN] nothing was identifiable; the well was even a block (it *is* concentric circles in `_symbol`;
    [EN] being classified as a "fixture" is what routed it here). And hatching is a **section/material**
    [EN] mark, not furniture: a room full of stripes hides everything. => Shape and size now come from
    [EN] `image_gen.furniture` (**one** table): shapes follow architectural furniture symbols (rectangle
    [EN] plus dividers / folded corner / burners / concentric circles), sizes follow real proportions
    [EN] (counter 48x16, bed 38x54, well 22 across). **Drawing and sizing share one source**, so packing
    [EN] at 48 wide can never be drawn at 40. ★ The position comes from `roomplan._pack_fixtures`
    [EN] (which knows where the walls and doors are); this function **only decides appearance**.
    """
    FR.draw(shapes, box, name, pal, font=font, here=here)
    # ★★★ 2026-10-27（用户：「家具都没了啊」）：**名字丢了**。
    #   上一版把这段换成了 `FR.draw(...)`，而 `FR.draw` 只管"长什么样"、不写字 ——
    #   于是我删掉了旧版末尾那句 `_label(...)`，图上只剩几个没名字的浅色小方块，
    #   在 940×600 的画布上看起来就是"什么都没画"。
    #   ⇒ 名字必须画，而且要**贴在不靠墙的那一侧**（贴着墙写字会被墙线穿过去），
    #     还要**互相避让**（两件家具挨着时名字会叠在一起）。
    # [EN] ★★★ 2026-10-27 (the user: "the furniture is all gone"): **the names were lost**. The
    # [EN] previous change replaced this with `FR.draw(...)`, which only decides appearance and writes
    # [EN] nothing -- so the old trailing `_label(...)` disappeared and the map kept only a few
    # [EN] unnamed pale rectangles, which on a 940x600 canvas reads as "nothing is drawn". => The name
    # [EN] must be drawn, **on the side away from the wall** (text against a wall gets a line through
    # [EN] it), and labels must **avoid each other** (adjacent pieces would overlap).
    _label_fixture(shapes, box, name, pal, font, room)


def _symbol(shapes: list, cx: float, cy: float, p: Place, pal: dict,
            font: str | None, here: bool, *, bounds=None, occupied=None) -> None:
    """一个**地点记号**：井画同心圆（水井的老记号），其余按字形给个小图示。

    ★★★ 2026-10-14（用户）：「大地图里还有有一个红圆形 旁边标记名字
    大地图里也不要这个红色圆形」。
    原来 `here=True` 时会在记号中心盖一个**半径 15 的实心红圆**（`pal['here']`
    = 朱砂），名字也染红色 —— 用户要的就是"去掉这个红圆"。

    ⚠ **和 `minimap.py` 保持一致**：小地图那边用户报过**三次**红点，早就改成
      "**当前地点 = 名字用朱砂 + 加粗 + 大一号**，不画任何点/圆"
      （见 `minimap.build_shapes` 里 `bold=here` 那一行及其注释：
       "颜色和字重就是全部层次"）。大地图这一处当时**漏改了** ——
       同一个毛病在两个渲染器里各写一份，就会漏。
    ⇒ 现在两边同一套：**没有实心红圆**，"我在这"只靠名字的颜色与字重。
    [EN] ★★★ 2026-10-14 (user): "the big map still has a red circle with the name beside it; drop that
    [EN] red circle in the big map too." The old code stamped a **filled red circle of radius 15**
    [EN] (`pal['here']` = cinnabar) onto the symbol when `here=True`, and tinted the name red.
    [EN] ⚠ **Keep in step with `minimap.py`**: the user reported that red dot **three times** on the
    [EN] minimap, which was long ago changed to "**current place = its name in cinnabar + bold + one
    [EN] size larger**, no dot/circle at all" (see `minimap.build_shapes`'s `bold=here` line and its
    [EN] comment: "colour and weight are the entire hierarchy"). This spot in the big map was **missed**
    [EN] at the time -- the same flaw written twice, once per renderer, is how that happens.
    [EN] => Both now share one convention: **no filled red circle**; "here" is only the name's colour
    [EN] and weight.
    """
    if '井' in p.name or '泉' in p.name:
        for r, wd in ((11, 1.8), (7, 1.4), (3, 1.2)):
            shapes.append(fcv.Circle(cx, cy, r,
                                     paint=ft.Paint(color=pal['ink'], stroke_width=wd,
                                                    style=ft.PaintingStyle.STROKE)))
    else:
        shapes.extend(MM._glyph(p.shape, cx, cy, 9.0, pal['ink'],
                                paper=pal['paper']))
    # ★★ 2026-10-16（用户）：符号的名字也放到符号**外侧**、且避开别的符号 / 名字。
    #   符号的 bbox 取同心圆 r=11（井）或字形 scale=9；名字在 8 个候选位里挑首个
    #   不与 `occupied` 重叠者（都重叠则取重叠最小者）。`bounds` 限制不画出绘图区。
    # [EN] ★★ 2026-10-16 (the user): a symbol's name also goes **outside** the symbol and avoids
    # [EN] other symbols / names. The symbol's bbox is the concentric circle r=11 (well) or the glyph
    # [EN] scale=9; the name picks, among 8 candidates, the first not overlapping `occupied`
    # [EN] (least-overlapping if all overlap). `bounds` keeps it inside the drawing area.
    sr = 11.0 if ('井' in p.name or '泉' in p.name) else 9.0
    sbox = (cx - sr, cy - sr, cx + sr, cy + sr)
    disp = p.name if here else p.label()
    lsize = 12 + (1 if here else 0)
    lw, lh = LP.est_text_size(disp, lsize)
    lx, ly = LP.place_label(sbox, lw, lh, list(occupied or []),
                            bounds=bounds, prefer='bottom-right')
    _label(shapes, lx, ly, disp, pal=pal,
           color=pal['here'] if here else pal['ink'], font=font,
           size=lsize, width=lw, bold=here)


# ══════════════════════════════════════════════════════════════════
#  ② 街道 / 城镇大图（不画室内，只标记建筑 —— 用户点名的第三种）
# [EN] ② Large street / town map (no indoor drawing, buildings marked only -- the user's third case)
# ══════════════════════════════════════════════════════════════════
def _draw_street(shapes: list, layout, places: list, px, pal: dict,
                 font: str | None, span: tuple | None = None) -> None:
    """街道图：**路画成双线**（普通地图的画法），建筑画成带阴影的小块。
    [EN] Street map: **roads as double lines** (ordinary map convention), buildings as small
    [EN] shaded blocks."""
    pos = {p.name: px(p) for p in places}
    # ① 水系（宽一些，画成一条带）
    # [EN] ① Water system (wider, drawn as a band)
    if len(getattr(layout, 'water', None) or []) >= 2:
        pts = [px(Place('', x=a, y=b)) for a, b in layout.water]
        els = [fcv.Path.MoveTo(pts[0][0], pts[0][1])]
        els += [fcv.Path.LineTo(x, y) for x, y in pts[1:]]
        shapes.append(fcv.Path(els, paint=ft.Paint(
            color=pal['water'], stroke_width=13.0, stroke_cap=ft.StrokeCap.ROUND,
            style=ft.PaintingStyle.STROKE)))
    # ② 街道：双线（外宽内纸），一眼是"一条路"而不是"一根线"
    # [EN] ② Streets: double line (wide outside, paper inside) so it reads as "a road", not "a line"
    for lk in (getattr(layout, 'links', None) or []):
        a, b = pos.get(lk.get('a')), pos.get(lk.get('b'))
        if not (a and b):
            continue
        shapes.append(fcv.Line(a[0], a[1], b[0], b[1],
                               paint=ft.Paint(color=pal['wall'], stroke_width=9.0,
                                              stroke_cap=ft.StrokeCap.ROUND,
                                              style=ft.PaintingStyle.STROKE)))
        shapes.append(fcv.Line(a[0], a[1], b[0], b[1],
                               paint=ft.Paint(color=pal['paper'], stroke_width=6.0,
                                              stroke_cap=ft.StrokeCap.ROUND,
                                              style=ft.PaintingStyle.STROKE)))
    # ③ 建筑：**只标记**（不画室内），大小按 `size` 分档
    #   ★★ 2026-10-16（用户）：「建筑名字放到建筑外面 … 放到外面的时候也要注意
    #     不要跟现有的东西覆盖」。⇒ 每个名字都用 `label_place.place_label` 在楼块**外侧**
    #     挑一个不与别的楼块 / 别的名字重叠的位置（8 个候选位取首个不重叠者；
    #     都重叠则取重叠最小者）。`bounds=span` 保证名字不画出绘图区。
    # [EN] ③ Buildings: **marked only** (no interior), sized by `size` tier
    # [EN] ★★ 2026-10-16 (the user): "put the building name outside the building ... and when
    # [EN] outside, also take care not to cover existing things." => each name uses
    # [EN] `label_place.place_label` to pick, **outside** the block, a position that overlaps no
    # [EN] other block / name (8 candidates, first non-overlapping; least-overlapping if all overlap).
    # [EN] `bounds=span` keeps the name inside the drawing area.
    blocks = {}
    for p in places:
        cx, cy = pos[p.name]
        r = 13.0 * MM._SIZE_SCALE.get(p.size, 1.0)
        blocks[p.name] = (cx - r, cy - r * 0.8, cx + r, cy + r * 0.8)
        _block(shapes, cx, cy, r, pal)
    drawn: list = []
    for p in places:
        bx0, by0, bx1, by1 = blocks[p.name]
        disp = p.name
        lw, lh = LP.est_text_size(disp, 12)
        occ = [b for n, b in blocks.items() if n != p.name] + drawn
        lx, ly = LP.place_label((bx0, by0, bx1, by1), lw, lh, occ,
                                bounds=span, prefer='bottom')
        drawn.append((lx, ly, lw, lh))
        _label(shapes, lx, ly, disp, pal=pal, color=pal['ink'],
               font=font, size=12, width=lw)


def _block(shapes: list, cx: float, cy: float, r: float, pal: dict) -> None:
    """一个建筑块：矩形 + 斜阴影（"这是房子"的通用记号）。
    [EN] One building block: rectangle + diagonal shading (the generic "this is a house" symbol)."""
    x0, y0, w, h = cx - r, cy - r * 0.8, 2 * r, 1.6 * r
    shapes.append(fcv.Rect(x0, y0, w, h, border_radius=1.5,
                           paint=ft.Paint(color=pal['furniture'],
                                          style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Rect(x0, y0, w, h, border_radius=1.5,
                           paint=ft.Paint(color=pal['wall_hi'], stroke_width=1.4,
                                          style=ft.PaintingStyle.STROKE)))
    k = 4.0
    while k < w + h:
        ax, ay = x0 + min(k, w), y0 + max(0.0, k - w)
        bx, by = x0 + max(0.0, k - h), y0 + min(k, h)
        shapes.append(fcv.Line(ax, ay, bx, by,
                               paint=ft.Paint(color=pal['wall_hi'], stroke_width=0.7,
                                              style=ft.PaintingStyle.STROKE)))
        k += 7.0


# ══════════════════════════════════════════════════════════════════
#  ③ 左上角的信息框（地点 · 时间 · 图例 · 比例尺）
# [EN] ③ The info box in the top-left (location · time · legend · scale bar)
# ══════════════════════════════════════════════════════════════════
#  用户原话：「地图**左上角带基本信息** 包括**地点 时间 图例 比例尺**
#            （**按照地图的方法在一个方框里**）」
#  ★ "按照地图的方法"在这里落成三件事：
#    ① 图例的记号**真的画一遍**（不是写文字说明"虚线表示路"）；
#    ② 比例尺是**一段带刻度的尺**（黑白相间），不是一句"1:100"；
#    ③ 全都**圈在一个方框里**，方框压在图的左上角。
#  ⚠ 比例尺上**不写"米 / 尺"这类真实单位** —— 我们没有真实尺寸，
#    写上去就是编。照实标「示意」。
# [EN] The user's exact words: "the map carries **basic information in its top-left**, including
# [EN] **location, time, legend, scale bar** (**in a box, the way maps do it**)".
# [EN] ★ "The way maps do it" comes down to three things here:
# [EN]   ① the legend symbols are **actually drawn** (not text saying "a dashed line means a road");
# [EN]   ② the scale bar is **a graduated ruler** (alternating black and white), not a sentence
# [EN]      saying "1:100";
# [EN]   ③ all of it **enclosed in a box**, pressed onto the map's top-left.
# [EN] ⚠ The scale bar carries **no real units like metres/feet** -- we have no real dimensions, and
# [EN]   writing them would be fabrication. It truthfully says "schematic".
def _info_box(shapes: list, pal: dict, layout, detail: str, *, place: str = '',
              when: str = '', font: str | None) -> None:
    """左上角的**图例区**：地点 / 时间 / 细致程度 / 图例 / **比例尺**。

    ★★ 2026-10-12 改（用户两条）：
      · 「左上角的图例 有些字在方框外面」—— 图例条目**画满了还往外溢**（原来只有
        148px 高的方框装 5 条图例 + 标题 + 比例尺，最后一条必然出框）；
      · 「不要带方框了 但是要注意**地图部分不要跟图例重合**」。
    ⇒ 那时起：**不画边框**、比例尺**挪到左下角**，并且把这块地方的高度按实际条目
      算出来（`legend_height()`）—— 绘图区按这个高度让位，"不重合"是**算出来的**。

    ★★★ 2026-10-24：比例尺**又搬回来了**，就在图例最后一条下面（用户：「大地图比例尺
      又被挡住了 请把比例尺后续就放到图例的下面」）。所以这里现在**也画比例尺** ——
      左下角那一带是地图内容的下沿，谁画在那儿都会被看成"被挡住"；左边这一列没有
      别的东西，接在图例下面最干净。位置走 `scale_origin()`，与 `legend_height()`
      同源（它把比例尺的高度也算进了让位里）。

    ★ 为什么仍然要"占位"：不画框不等于不占地方。图例文字落在图上一样会挡住内容 ——
      用户要的是"没有框"，不是"图例和地图叠在一起"。
    [EN] The **legend area** in the top-left: location / time / level of detail / legend / **scale
    [EN] bar**.
    [EN] ★★ Changed 2026-10-12 (two things from the user):
    [EN] · "in the top-left legend **some text is outside the box**" -- the legend entries
    [EN]   **overflowed** (the old 148px box had to hold 5 entries + a title + the scale bar, so the
    [EN]   last entry necessarily fell outside);
    [EN] · "no box any more, but note that **the map part must not overlap the legend**".
    [EN] ⇒ Since then: **no border is drawn**, the scale bar **moved to the bottom-left**, and the
    [EN] block's **height is computed from the actual entries** (`legend_height()`) -- the drawing
    [EN] area gives way by that height, so "no overlap" is **computed**, not eyeballed.
    [EN] ★★★ 2026-10-24: the scale bar **moved back**, right below the last legend entry (the user:
    [EN] "the big map's scale bar is covered again -- from now on put it below the legend"). So this
    [EN] function now **draws the scale bar too**: the bottom-left is the map content's lower edge, and
    [EN] anything drawn there reads as "covered"; the left column has nothing else in it, so hanging the
    [EN] scale below the legend is the cleanest place. Its position comes from `scale_origin()`, which
    [EN] shares its arithmetic with `legend_height()` (that one now includes the scale block's height).
    [EN] ★ Why it still reserves space: no border does not mean no room. Legend text landing on the
    [EN] map hides content just the same -- the user asked for "no box", not "legend on top of the
    [EN] map".
    """
    x0, y0 = LEG_X0, LEG_Y0
    y = y0 + INFO_PAD
    title = (place or _bldg_name(layout) or t('（待定）'))
    shapes.append(MM._text(x0 + INFO_PAD, y - 3, title, size=15,
                           color=pal['ink'], font=font, bold=True))
    y += LEG_DY_TITLE
    shapes.append(MM._text(x0 + INFO_PAD, y - 3,
                           t('时间：{w}', w=when or t('（未记）')), size=11,
                           color=pal['muted'], font=font))
    y += LEG_DY_WHEN
    shapes.append(MM._text(x0 + INFO_PAD, y - 3, t('细致程度：{d}', d=detail), size=11,
                           color=pal['muted'], font=font))
    y += LEG_DY_DETAIL
    # ★★★ 2026-10-27：**没有条目就不画"图例"这两个字**。
    #   城市/城际/甲板的图例在右下角（各有自己的函数），左边这张表返回空 ——
    #   这时还留一个"图例"标题、下面一条都没有，读者会以为图例没画出来。
    # [EN] ★★★ 2026-10-27: **no entries, no "legend" heading**. The city / region / deck legends live
    # [EN] in the bottom-right (each has its own function), and this table returns empty for them; a
    # [EN] "legend" heading with nothing under it reads as "the legend failed to draw".
    _items = legend_items(detail)
    if _items:
        shapes.append(MM._text(x0 + INFO_PAD, y - 4, t('图例'), size=12, color=pal['ink'],
                               font=font, bold=True))
        y += LEG_DY_HEAD
        for kind, text in _items:
            _legend_mark(shapes, x0 + INFO_PAD + 8, y + 4, kind, pal)
            shapes.append(MM._text(x0 + INFO_PAD + 30, y - 3, text, size=11,
                                   color=pal['muted'], font=font))
            y += LEG_ITEM_H

    # ★★★ 2026-10-24：比例尺**接着图例最后一条往下画**（用户：「请把比例尺后续就放到
    #   图例的下面」）。位置**不在这里自己算** —— 走 `scale_origin()`，因为
    #   `legend_height()`（给绘图区让位用）算的是同一件事，两处各算一次必漂。
    # [EN] ★★★ 2026-10-24: the scale bar is drawn **right below the last legend entry** (the user:
    # [EN] "from now on put the scale bar below the legend"). Its position is **not** computed here
    # [EN] -- it goes through `scale_origin()`, because `legend_height()` (which reserves room for the
    # [EN] drawing area) computes the same thing, and two implementations always drift.
    _sx, _sy = scale_origin(detail)
    _scale_bar(shapes, _sx, _sy, pal, font=font)


def layout_area(W: int, H: int, detail: str) -> tuple:
    """绘图区 `(ox, oy, cw, ch)` —— **产品与判据共用的唯一一份**。

    ★ 为什么要抽出来：`span` 与 `px` 都从它派生。判据（与探针）如果自己再算一遍，
      就又成了"两套口径" —— 2026-10-12 实测过一次这种漂移的代价：
      解算按画布宽换算、绘制按绘图区宽换算，家具因此跑到墙外。
    [EN] The drawing area `(ox, oy, cw, ch)` -- **the one definition shared by the product and the
    [EN] criteria**.
    [EN] ★ Why extract it: both `span` and `px` derive from it. If a criterion (or a probe) computes
    [EN] it again, that is "two definitions" again -- measured once on 2026-10-12 what drift costs:
    [EN] solving mapped from canvas width while drawing mapped from drawing-area width, which pushed
    [EN] the furniture outside the wall.
    """
    ox = INFO_W + 26
    oy = max(26.0, legend_height(detail) + 12)
    # ★★★ 2026-10-24（用户：「**大地图比例尺又被挡住了** 请把比例尺后续就放到图例的下面」）：
    #   比例尺已经**搬进图例区**（`scale_origin()`），底部不再是"比例尺的地盘"，
    #   于是这里的留白从"给它让位"变成"一圈呼吸位"（`BOTTOM_PAD`）。
    #   ⚠ 别把这条留白当装饰：它同时是"地图内容不许压到指北针"的唯一靠山。
    # [EN] ★★★ 2026-10-24 (user: "**the big map's scale bar is covered again** -- from now on put the
    # [EN] scale bar below the legend"): the scale bar has **moved into the legend area**
    # [EN] (`scale_origin()`), so the bottom is no longer "the scale bar's territory" and this padding
    # [EN] goes from "reserve room for it" to "a margin" (`BOTTOM_PAD`).
    # [EN] ⚠ Not decoration: it is the only thing that keeps map content off the north arrow.
    return ox, oy, W - ox - 26, H - oy - BOTTOM_PAD


def layout_px(W: int, H: int, detail: str):
    """归一化 → 像素的换算函数（**产品与判据共用的唯一一份**）。
    [EN] The normalised-to-pixel mapping function (**the one definition shared by the product and the
    [EN] criteria**)."""
    ox, oy, cw, ch = layout_area(W, H, detail)
    return lambda p: (ox + 14 + p.x * (cw - 28), oy + 14 + p.y * (ch - 28))


def layout_span(W: int, H: int, detail: str) -> tuple:
    """给 `plan_audit.solve()` 的那块 `span`（**与绘图区同一份**）。
    [EN] The `span` handed to `plan_audit.solve()` (**the same one as the drawing area**)."""
    ox, oy, cw, ch = layout_area(W, H, detail)
    return (ox + 14, oy + 14, ox + cw - 14, oy + ch - 14)


def legend_text_bottom(detail: str) -> float:
    """图例**最后一条文字**之下那个 y（比例尺从这里往下排）。

    ★ 只在 `legend_height()` / `scale_origin()` 里用 —— 它们是同一个和式的两截，
      所以行距全部取自 `LEG_DY_*` / `LEG_ITEM_H`，不再各写一份字面量。
    [EN] The y just **below the last legend entry** (the scale bar is laid out from here).
    [EN] ★ Used only by `legend_height()` / `scale_origin()` -- they are two halves of the same sum,
    [EN] so every line step comes from `LEG_DY_*` / `LEG_ITEM_H` instead of being written twice.
    """
    return (LEG_Y0 + INFO_PAD + LEG_DY_TITLE + LEG_DY_WHEN + LEG_DY_DETAIL + LEG_DY_HEAD
            + LEG_ITEM_H * len(legend_items(detail)))


def legend_height(detail: str) -> float:
    """图例区**实际占多高**（含地点/时间/细致程度那三行，**以及比例尺那一块**）。

    ★ 这个函数存在的唯一理由：让绘图区**算得出**自己该从哪儿开始 ——
      "图例与地图不重合"于是成了可验证的事（判据会量它）。
    ★★★ 2026-10-24：比例尺搬进图例区之后，它的高度**也是这块地方的一部分**
      （`SCALE_GAP + SCALE_BLOCK_H`）—— 漏掉它，绘图区就会从比例尺身上开始，
      用户看到的正是"比例尺被挡住"。
    [EN] How tall the legend area **actually is** (including the location/time/detail lines **and the
    [EN] scale block**).
    [EN] ★ The only reason this function exists: so the drawing area can **compute** where it starts
    [EN] -- "the legend does not overlap the map" thus becomes verifiable (a criterion measures it).
    [EN] ★★★ 2026-10-24: now that the scale bar lives in the legend area, its height is **part of this
    [EN] block** (`SCALE_GAP + SCALE_BLOCK_H`); omit it and the drawing area starts on top of the scale
    [EN] bar -- exactly the "covered scale bar" the user reported.
    """
    # ★ 只由 `detail` 决定（条目数跟着细致程度走）。**不许再引入"画不画某一条"这种
    #   调用方可能忘传的参数** —— 那会让 `layout_area()` / `plan_audit.solve()` / 判据
    #   三处各算一次、几何漂 15px（2026-10-22 实测：房间名离上墙 9px，G1/G3 当场红）。
    # [EN] Determined by `detail` alone (the entry count follows the level of detail). **Never add a
    # [EN] "whether to draw entry X" parameter again** -- a caller may forget it, the three places
    # [EN] (`layout_area()`, `plan_audit.solve()`, criteria) then disagree and the geometry shifts by
    # [EN] 15px (measured 2026-10-22: the room name sat 9px off the top wall, G1/G3 went red).
    return legend_text_bottom(detail) + SCALE_GAP + SCALE_BLOCK_H + INFO_PAD


def scale_origin(detail: str) -> tuple:
    """比例尺在图例区里的位置 `(x, 尺身顶的 y)` —— **产品与判据共用的唯一一份**。

    返回的 y 是**尺身**顶（`_scale_bar` 的 `y`），标题画在 `y - 13`。
    [EN] The scale bar's position inside the legend area `(x, the y of the ruler body)` -- **the one
    [EN] definition shared by the product and the criteria**. The returned y is the **ruler's** top
    [EN] (`_scale_bar`'s `y`); the title is drawn at `y - 13`.
    """
    return SCALE_X, legend_text_bottom(detail) + SCALE_GAP + 13.0


def _legend_mark(shapes: list, cx: float, cy: float, kind: str, pal: dict) -> None:
    """图例里那个**记号本身**（照实画一遍，不是写文字）。
    [EN] The **symbol itself** in the legend (actually drawn, not described in words)."""
    if kind == 'wall':
        for i in (0, 2.5):
            shapes.append(fcv.Rect(cx - 8 + i, cy - 4 + i, 16 - 2 * i, 8 - 2 * i,
                                   paint=ft.Paint(color=pal['wall_hi'], stroke_width=1.1,
                                                  style=ft.PaintingStyle.STROKE)))
    elif kind == 'door':
        # ★★ 2026-10-22：图例里的门记号**照图上新画法**（缺口 + 一条门扇线）。
        #   以前这里画的是"缺口 + 开合弧"，而图上的门已经改成"缺口 + 门扇"——
        #   **图例与图上不一致**，看的人会对不上（那正是"图例里那条跟图上那条不是一回事"）。
        #   所以这里用同一个构图：墙带（两段，中间断开）+ 缺口 + 门扇。
        # [EN] ★★ 2026-10-22: the legend's door mark **copies the new drawing** (opening + one leaf
        # [EN] line). It used to be "opening + swing arc" while the map's doors had already changed to
        # [EN] "opening + leaf" -- **the legend and the map disagreed**, so the reader could not match
        # [EN] them. Same composition here: wall band (two segments, broken in the middle) + opening +
        # [EN] one leaf.
        _gap = 7.0
        for x0, x1 in ((cx - 9, cx - _gap / 2), (cx + _gap / 2, cx + 9)):
            shapes.append(fcv.Line(x0, cy, x1, cy,
                                   paint=ft.Paint(color=pal['wall_hi'], stroke_width=1.7,
                                                  style=ft.PaintingStyle.STROKE)))
        shapes.append(fcv.Line(cx - _gap / 2, cy, cx + _gap / 2, cy,
                               paint=ft.Paint(color=pal['paper'], stroke_width=WALL_T * 2 + 1.0,
                                              style=ft.PaintingStyle.STROKE)))
        shapes.append(fcv.Line(cx - _gap / 2, cy, cx - _gap / 2, cy - _gap,
                               paint=ft.Paint(color=pal['wall_hi'], stroke_width=1.3,
                                              style=ft.PaintingStyle.STROKE)))
    elif kind == 'furn':
        shapes.append(fcv.Rect(cx - 8, cy - 4, 16, 8,
                               paint=ft.Paint(color=pal['furniture'],
                                              style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Rect(cx - 8, cy - 4, 16, 8,
                               paint=ft.Paint(color=pal['wall_hi'], stroke_width=1.0,
                                              style=ft.PaintingStyle.STROKE)))
    elif kind == 'frame':
        shapes.append(fcv.Rect(cx - 8, cy - 4, 16, 8,
                               paint=ft.Paint(color=pal['ink'], stroke_width=1.3,
                                              style=ft.PaintingStyle.STROKE)))
    elif kind == 'ground':
        for dx in (-6, 0, 6):
            for dy in (-2, 2):
                shapes.append(fcv.Circle(cx + dx, cy + dy, 0.8,
                                         paint=ft.Paint(color=pal['wall'],
                                                        style=ft.PaintingStyle.FILL)))
    elif kind == 'path':
        # 通路（廊 / 甬道）：图例里**必须画成虚线**，与图上那两条一致 ——
        # 画成实线会让人以为是墙，画成「街道」那种双线又跟整体图混在一起。
        # [EN] Path (corridor): the legend **must show dashes**, matching the two on the map.
        # [EN] A solid mark reads as a wall, and the double-line "street" mark belongs to the
        # [EN] overview map.
        for seg in 0, 6:
            shapes.append(fcv.Line(cx - 9 + seg, cy, cx - 2 + seg, cy,
                                   paint=ft.Paint(color=pal['link'], stroke_width=2.0,
                                                  style=ft.PaintingStyle.STROKE)))
    elif kind == 'road':
        # ★★★ 2026-10-26：室内图不再画路（见 `_draw_plan` 的 ③），这个记号现在**只服务室外图**
        #   （`details_whole` / 街道图 / 城市图），所以宽度回到 `_draw_street` 那一套（9 / 6）——
        #   与图上真出现的那条一致。`ROAD_OUTER/ROAD_INNER`（7 / 4.2）是室内版的参数，已随那一段删掉。
        # [EN] ★★★ 2026-10-26: the indoor plan no longer draws roads (see section 3 of `_draw_plan`),
        # [EN] so this mark now **only serves outdoor maps** (street / city), and its width returns to
        # [EN] the `_draw_street` values (9 / 6) so it matches what actually appears. The 7 / 4.2 pair
        # [EN] was the indoor parameters and went away with that block.
        for w, color in ((9.0, pal['wall']), (6.0, pal['paper'])):
            shapes.append(fcv.Line(cx - 9, cy, cx + 9, cy,
                                   paint=ft.Paint(color=color, stroke_width=w,
                                                  stroke_cap=ft.StrokeCap.ROUND,
                                                  style=ft.PaintingStyle.STROKE)))
    elif kind == 'water':
        shapes.append(fcv.Line(cx - 9, cy, cx + 9, cy,
                               paint=ft.Paint(color=pal['water'], stroke_width=3.0,
                                              style=ft.PaintingStyle.STROKE)))
    else:                                   # bldg / bldg_s
        r = 6.0 if kind == 'bldg' else 4.0
        shapes.append(fcv.Rect(cx - r, cy - r * 0.7, 2 * r, 1.4 * r,
                               paint=ft.Paint(color=pal['furniture'],
                                              style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Rect(cx - r, cy - r * 0.7, 2 * r, 1.4 * r,
                               paint=ft.Paint(color=pal['wall_hi'], stroke_width=1.0,
                                              style=ft.PaintingStyle.STROKE)))


#: 比例尺画几格、每格多少像素。
# [EN] : how many cells the scale bar has and how many pixels each.
SCALE_CELLS, SCALE_CELL_W = 4, 26


def _scale_bar(shapes: list, x: float, y: float, pal: dict,
               font: str | None) -> None:
    """比例尺：**一段黑白相间的带刻度的尺** + 「示意」两个字。

    ⚠ 刻度上写的是**格子数**（`0 1 2 3 4`），不是米/尺 —— 我们没有真实尺寸。
      写真实单位就是编，而这个项目对"编"最不客气。
    [EN] Scale bar: **a graduated band alternating black and white** + the word "schematic".
    [EN] ⚠ The graduations read **cell counts** (`0 1 2 3 4`), not metres/feet -- we have no real
    [EN] dimensions. Writing real units would be fabrication, and this project is harshest about
    [EN] fabrication.
    """
    h = 9.0
    shapes.append(MM._text(x, y - 13, t('比例尺（示意）'), size=11, color=pal['ink'],
                           font=font, bold=True))
    for i in range(SCALE_CELLS):
        bx = x + i * SCALE_CELL_W
        shapes.append(fcv.Rect(bx, y, SCALE_CELL_W, h,
                               paint=ft.Paint(
                                   color=pal['ink'] if i % 2 == 0 else pal['paper'],
                                   style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Rect(bx, y, SCALE_CELL_W, h,
                               paint=ft.Paint(color=pal['ink'], stroke_width=0.9,
                                              style=ft.PaintingStyle.STROKE)))
        shapes.append(MM._text(bx - 2, y + h + 1, str(i), size=9,
                               color=pal['muted'], font=font))
    shapes.append(MM._text(x + SCALE_CELLS * SCALE_CELL_W - 6, y + h + 1,
                           str(SCALE_CELLS), size=9, color=pal['muted'], font=font))


def _north(shapes: list, W: int, H: int, pal: dict, font: str | None) -> None:
    """右下角的**指北针**（地图的通行记号）。
    [EN] The **north arrow** in the bottom-right (a universal map symbol)."""
    cx, cy = W - 42.0, H - 46.0
    shapes.append(fcv.Path([fcv.Path.MoveTo(cx, cy - 16),
                            fcv.Path.LineTo(cx + 7, cy + 10),
                            fcv.Path.LineTo(cx, cy + 4),
                            fcv.Path.LineTo(cx - 7, cy + 10),
                            fcv.Path.Close()],
                           paint=ft.Paint(color=pal['ink'],
                                          style=ft.PaintingStyle.FILL)))
    shapes.append(MM._text(cx - 2, cy - 30, t('北'), size=11, color=pal['ink'],
                           font=font, center=True))


def _yard_label_dy(plan, yy0: float, span: tuple, *, size: float = 15.0) -> float:
    """院名要不要往下让一格（避免与楼名写在同一行）。

    ★ 判据是**几何**："院子上沿"与"房子外框上沿"是不是同一条线（±3px）。
      是 ⇒ 让开 `size + 4`（一个字高 + 行距）；不是 ⇒ 不动。
    ★ 为什么不用"楼名有没有画"：楼名可能读不出来（`_bldg_name` 返回空），
      那时院名不必让；而"两条上沿重合"是个客观条件，与有没有写字无关 ——
      让开一格最多是多一点留白，不会错。
    [EN] Whether the courtyard name must drop one line to avoid the building name.
    ★ The test is **geometric**: is the courtyard's top edge the same line (+-3px) as the house
    [EN] frame's top edge? If so drop by `size + 4`; otherwise leave it. ★ Why not "is the building name
    [EN] drawn": that name may be unreadable (`_bldg_name` returns empty) and then no shift is needed,
    [EN] whereas "the two top edges coincide" is objective and independent of any text -- dropping a
    [EN] line at worst leaves a little whitespace.
    """
    house = getattr(plan, 'house', None)
    if house is None:
        return 0.0
    if abs(float(house[1]) - float(yy0)) > 3.0:
        return 0.0
    # 楼名写在 `span[1] + 4` 那条带上：院子上沿也进了那条带才需要让
    if float(yy0) > float(span[1]) + size + 10.0:
        return 0.0
    return size + 4.0


def _label(shapes: list, x: float, y: float, text: str, *, pal: dict, color: str,
           font: str | None, size: int = 12, width: float = 60,
           bold: bool = False) -> None:
    """居中写在 `x..x+width` 之间的一个字块（**文字不越界**，免得压在别人身上）。

    `bold` 透传给 `MM._text` —— 2026-10-14 起"当前地点"靠**朱砂 + 加粗**表示
    （不再画实心红圆，见 `_symbol` 的注释）。
    [EN] A text block centred between `x..x+width` (**text stays inside**, so it doesn't press onto
    [EN] others). `bold` is passed through to `MM._text` -- since 2026-10-14 the "current place" is shown
    [EN] by **cinnabar + bold** (no more filled red circle, see `_symbol`'s comment).
    """
    tw = MM._cjk_w(str(text or ''), size)
    shapes.append(MM._text(x + max(0.0, (width - tw) / 2), y, text, size=size,
                           color=color, font=font, bold=bold))




#: **只用来认"整栋楼叫什么"的后缀字**（`临河楼` / `藏经阁` / `兰若寺`）。
#:
#: ★★★ 2026-10-27（重绘现有地图时抓到的真 bug）：室内图上的**楼名**原来是
#:   `frame or caption` —— 而 `caption` 是**河边题记**（"壶在"这种），两个字段语义
#:   完全不同却互相兜底。实测那份室内图的楼名位置写着 **"壶在"**（一个不成词的碎片），
#:   而真正的"临河楼"一个字都没出现。用户看到的就是"图上有个莫名其妙的字"。
#: ⇒ 楼名只认**三个**来源（按可靠性）：`frame`（美术给的框名）→ `program.地点`
#:   → 地点里**后缀命中下面这张表**的那一处。都没有就**不写**（宁可不写楼名，
#:   也不要写一个错的）。
#:
#: ⚠ 这张表刻意很短，且**不收** `院/屋/房/厅/室/间/门/店`：那些正是房间自己的字，
#:   收进来会让"后院"变成楼名。这张表的每个字都几乎不会单独作房间名。
#: [EN] Suffix characters for recognising **the whole building's name** (`临河楼`, `藏经阁`,
#: [EN] `兰若寺`). ★★★ 2026-10-27 (a real bug found while re-drawing the live maps): the indoor plan's
#: [EN] building name used to be `frame or caption` -- but `caption` is a **riverside inscription**
#: [EN] ("壶在", a meaningless fragment), two fields with completely different meanings standing in for
#: [EN] one another. Measured, the name band read **"壶在"** while the real 临河楼 never appeared.
#: [EN] => Only three sources, by reliability: `frame`, then `program.地点`, then the one place whose
#: [EN] name ends with a character in this table. With none of them, write **no** name (better no name
#: [EN] than a wrong one). ⚠ The table is deliberately short and **excludes** 院/屋/房/厅/室/间/门/店:
#: [EN] those belong to rooms, and including them turns 后院 into a building name.
BLDG_SUFFIX = ('楼', '阁', '塔', '寺', '观', '庵', '庙', '祠', '邸', '墅',
               '苑', '舫', '榭', '轩', '斋', '庄', '馆', '殿', '宫', '府')


def _bldg_name(layout, places=None) -> str:
    """这张室内图**画的是哪一栋楼**（没有就返回空串 —— 空是安全的）。

    ★ 三处来源，按可靠性排序，一处命中就返回：
      ① `layout.frame` —— 美术/上层明确给的"框上的建筑名"，最硬；
      ② 任务书里的 `地点` —— 那份任务书就是按这个名字解算的；
      ③ 地点里**以后缀字结尾**的那一处，且**只命中一处**时才用
         （两处都像楼 = 判断不了，宁可不写）。
    ★ 绝不回落到 `caption`：那是河边题记，不是楼名（2026-10-27 的 bug 就是这么来的）。
    [EN] Which building this indoor plan depicts (empty when unknown -- empty is safe). ★ Three
    [EN] sources by reliability: `layout.frame`, the program's `地点`, and the single place whose name
    [EN] ends with a building suffix (only when **exactly one** matches -- two candidates means "cannot
    [EN] tell", so write nothing). ★ Never fall back to `caption`: that is a riverside inscription, not a
    [EN] building name (exactly how the 2026-10-27 bug happened).
    """
    nm = str(getattr(layout, 'frame', '') or '').strip()
    if nm:
        return nm
    prog = getattr(layout, 'program', None) or {}
    if isinstance(prog, dict):
        nm = str(prog.get('地点') or '').strip()
        if nm:
            return nm
    ps = list(places if places is not None else (getattr(layout, 'places', None) or []))
    hits = []
    for p in ps:
        n = str(getattr(p, 'name', '') or '').strip()
        if len(n) >= 2 and n.endswith(BLDG_SUFFIX):
            hits.append(n)
    return hits[0] if len(hits) == 1 else ''


def _region_legend(shapes: list, pal: dict, info: dict, *, font: str | None = None,
                  span: tuple | None = None, style=None) -> None:
    """城际图的**符号图例**：画在绘图区右下角，只列**这张图上真出现了**的符号。

    ★ 为什么必须图例：城际图上的圆点大小（都城/县城/镇）、三角（山）、三条短横（水）
      是**约定符号** —— 不解释的话，读者只会看到"几个大小不一的点"，而"哪座城更重要"
      正是这张图唯一能传达的信息。
    ★ 为什么只列出现过的：把"运河""关隘"这些没出现在图上的符号也列出来，会让读者
      去找它们（"图上那条运河在哪儿？"）。图例只解释**看得见的东西**。
    ★★ 2026-10-26：等级的**说法**改由档案给（`style.rank_name`）。原来写死「州府/县城」——
      在一张西幻城堡图上写"县城"，读者会以为图画错了。判不出风格时用中性说法
      （"要地/据点/集镇/小聚落"），因为不知道是什么世界时，"县城"就是替作者断言了文明。
    ★★ 航路图（`nautical`）没有政区界，图例也就**不列政区**；港口列锚、航线列虚线。
    [EN] A **symbol legend** for the region map, bottom-right of the drawing area, listing only the
    [EN] symbols that actually appear. ★ Why it is required: dot sizes, the triangle (mountain) and
    [EN] the three short waves (water) are **conventional symbols** -- unexplained, the reader just
    [EN] sees "some dots of different sizes", while "which city matters" is the only information this
    [EN] map can carry. ★ Why only what appears: listing symbols that are absent sends the reader
    [EN] hunting for them. ★★ 2026-10-26: the **wording of each rank** now comes from the profile
    [EN] (`style.rank_name`); it used to be hard-coded "prefecture/county seat", which on a Western
    [EN] castle map looks like a mistake. When the profile is unknown the wording is neutral
    [EN] ("stronghold / outpost / market town / hamlet"), because naming a "county seat" asserts a
    [EN] civilisation the author never specified. ★★ A nautical chart has no political boundaries, so
    [EN] the legend lists none; ports get an anchor and routes are dashed.
    """
    items: list[tuple[str, str]] = []          # (种类, 说明)
    ranks = {r for _n, _x, _y, r in (info.get('nodes') or [])}
    # 等级说法：先问档案，问不到用中性词（`WS.rank_name` 已经做了这个兜底）
    # [EN] Rank wording: ask the profile, then fall back to neutral words (WS.rank_name handles it)
    for r in (4, 3, 2):
        if r not in ranks:
            continue
        label = WS.rank_name(style, r)
        if r == 2 and 1 in ranks:
            label = f"{label} / {WS.rank_name(style, 1)}"
        kind = {4: 'capital', 3: 'county', 2: 'town'}[r]
        items.append((kind, label))
    if 1 in ranks and 2 not in ranks:
        items.append(('town', WS.rank_name(style, 1)))
    if info.get('anchors'):
        items.append(('anchor', '港口 / 锚地'))
    if info.get('mountains'):
        items.append(('mountain', '山地'))
    if info.get('waters'):
        # 按**类型**写：河是一条带、湖是闭合水面、海是"实线海岸线 + 一侧整片水"。
        # 一句"水体（河湖）"对海边地图是**说错话** —— 图上根本没有湖。
        # [EN] Word it by **kind**: a river is a band, a lake a closed surface, a sea "a solid
        # coastline with water filling one side". One blanket "water body (river/lake)" is a
        # **wrong caption** on a seaside map -- there is no lake on it.
        items.append(('water', SM.WK_LABEL.get(info.get('water_kind') or '', '水体')))
    if info.get('roads'):
        if (info.get('form') or '') == SM.REGION_NAUTICAL:
            items.append(('route', '航路（按两端港口分粗细）'))
        else:
            items.append(('road', '道路（按两端等级粗细）'))
    if not items:
        return

    x0, y0, x1, y1 = span or (0.0, 0.0, float(W), float(H))
    pad = 8.0
    lh = 16.0                                  # 每行高度
    box_w = 132.0
    box_h = lh * len(items) + pad * 2
    bx = x1 - box_w - 10.0
    by = y1 - box_h - 10.0
    shapes.append(fcv.Rect(bx, by, box_w, box_h, border_radius=3.0,
                           paint=ft.Paint(color=_alpha(pal.get('paper', '#f8f4ea'), 0.92),
                                          style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Rect(bx, by, box_w, box_h, border_radius=3.0,
                           paint=ft.Paint(color=pal.get('link', '#c5bda9'), stroke_width=0.9,
                                          style=ft.PaintingStyle.STROKE)))
    for i, (kind, text) in enumerate(items):
        cy = by + pad + lh * i + lh / 2.0
        sx = bx + 16.0
        _legend_glyph(shapes, kind, sx, cy, pal)
        shapes.append(MM._text(bx + 34.0, cy - 6.5, text, size=10,
                               color=pal.get('ink', '#4a4f57'), font=font))


def _legend_glyph(shapes: list, kind: str, x: float, y: float, pal: dict) -> None:
    """图例里那个**小记号**（与图上用的是同一套画法，不是另画一个近似的）。
        English: The small **glyph** in the legend, drawn with the same code as on the map (never a
        lookalike).
    """
    ink = pal.get('ink', '#4a4f57')
    paper = pal.get('on_paper', '#fffdf8')
    if kind == 'capital':
        shapes.append(fcv.Circle(x, y, 4.6, paint=ft.Paint(color=ink,
                                                          style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Circle(x, y, 7.4, paint=ft.Paint(color=ink, stroke_width=1.0,
                                                          style=ft.PaintingStyle.STROKE)))
    elif kind == 'county':
        shapes.append(fcv.Circle(x, y, 4.0, paint=ft.Paint(color=ink,
                                                          style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Circle(x, y, 1.7, paint=ft.Paint(color=paper,
                                                          style=ft.PaintingStyle.FILL)))
    elif kind == 'town':
        shapes.append(fcv.Circle(x, y, 2.6, paint=ft.Paint(color=ink,
                                                          style=ft.PaintingStyle.FILL)))
    elif kind == 'mountain':
        shapes.append(fcv.Path([fcv.Path.MoveTo(x, y - 6.0), fcv.Path.LineTo(x + 5.6, y + 4.2),
                                fcv.Path.LineTo(x - 5.6, y + 4.2), fcv.Path.Close()],
                               paint=ft.Paint(color=ink, stroke_width=1.0,
                                              style=ft.PaintingStyle.STROKE)))
    elif kind == 'water':
        for k, dy in enumerate((-2.4, 0.0, 2.4)):
            hw = 7.0 - k * 1.2
            shapes.append(fcv.Line(x - hw, y + dy, x + hw, y + dy,
                                   paint=ft.Paint(color=pal.get('water', '#8fb0c4'),
                                                  stroke_width=1.6,
                                                  stroke_cap=ft.StrokeCap.ROUND)))
    elif kind == 'road':
        shapes.append(fcv.Line(x - 8, y, x + 8, y,
                               paint=ft.Paint(color=pal.get('wall', '#b9b1a0'),
                                              stroke_width=4.2,
                                              stroke_cap=ft.StrokeCap.ROUND)))
        shapes.append(fcv.Line(x - 8, y, x + 8, y,
                               paint=ft.Paint(color=paper, stroke_width=1.8,
                                              stroke_cap=ft.StrokeCap.ROUND)))
    elif kind == 'route':
        # 航路：虚线（海图上航线不是实线 —— 实线会被读成陆上的官道或堤）
        # [EN] Sea route: dashed (on a chart a solid line reads as a highway or a dyke on land)
        t = -9.0
        while t < 9.0:
            t2 = min(t + 4.0, 9.0)
            shapes.append(fcv.Line(x + t, y, x + t2, y,
                                   paint=ft.Paint(color=ink, stroke_width=1.4)))
            t = t2 + 2.4
    elif kind == 'anchor':
        # 锚（与图上 `scalemap._anchor_symbol` **同一形状**，只是小一号）
        # [EN] Anchor (the **same shape** as `scalemap._anchor_symbol`, only smaller)
        shapes.append(fcv.Line(x, y - 5.4, x, y + 5.0,
                               paint=ft.Paint(color=ink, stroke_width=1.3,
                                              stroke_cap=ft.StrokeCap.ROUND)))
        shapes.append(fcv.Line(x - 3.4, y - 3.0, x + 3.4, y - 3.0,
                               paint=ft.Paint(color=ink, stroke_width=1.3,
                                              stroke_cap=ft.StrokeCap.ROUND)))
        shapes.append(fcv.Circle(x, y - 5.6, 1.3, paint=ft.Paint(
            color=ink, stroke_width=1.2, style=ft.PaintingStyle.STROKE)))
        shapes.append(fcv.Line(x - 4.4, y + 2.4, x - 2.2, y + 4.6,
                               paint=ft.Paint(color=ink, stroke_width=1.3,
                                              stroke_cap=ft.StrokeCap.ROUND)))
        shapes.append(fcv.Line(x + 4.4, y + 2.4, x + 2.2, y + 4.6,
                               paint=ft.Paint(color=ink, stroke_width=1.3,
                                              stroke_cap=ft.StrokeCap.ROUND)))
        shapes.append(fcv.Line(x - 2.2, y + 4.6, x + 2.2, y + 4.6,
                               paint=ft.Paint(color=ink, stroke_width=1.3,
                                              stroke_cap=ft.StrokeCap.ROUND)))


#: 混色只留**一份实现**（在 `scalemap`）。这里不另抄一份 —— 同一件事两处实现必然漂
#: （本项目的头号老坑）。`_city_glyph` 里的图例记号必须与图上**同色同宽**，
#: 抄一份就等于给漂移留了一个入口。
# [EN] Colour mixing has **one implementation** (in `scalemap`). Do not copy it here -- two
# [EN] implementations of the same thing always drift (this project's worst recurring pit). The
# [EN] legend glyphs must match the map exactly, and a copy is an open door to drift.
_mix = SM._mix


def _alpha(hex_color: str, a: float) -> str:
    """给 `#rrggbb` 加不透明度，返回 `#aarrggbb`（flet 用 ARGB）。认不出的原样返回。
        English: Add opacity to `#rrggbb`, returning `#aarrggbb` (flet uses ARGB); pass through
        anything unrecognised.
    """
    s = str(hex_color or '').lstrip('#')
    if len(s) == 6:
        return '#%02x%s' % (int(max(0.0, min(1.0, a)) * 255), s)
    if len(s) == 8:
        return '#' + s
    return hex_color


def _city_legend(shapes: list, pal: dict, info: dict, *, font: str | None = None,
                 span: tuple | None = None) -> None:
    """城市图的**图例**：右下角一块，只列**这张图上真出现了**的要素。

    ## 为什么这个必须补（2026-10-26）

    城际图从做出来那天就有图例，城市图**一直没有**。而城市图恰恰是"符号最多"的那张：
    街区面、三档粗细的路、中心线、路口、绿面、分级圆点 —— 全都靠读者自己猜。
    标准地图的要素清单里，图例是最基本的一项（没有它，图就不是"图"而是"一堆形状"）。

    ## 列什么（按标准地图的要素表，只列有数据的）

    | 要素 | 有数据吗 | 怎么处理 |
    |---|---|---|
    | 街区面（地块） | ✓ Voronoi 切出来的 | 列 |
    | 道路分级 | ✓ 按两端规模推 | **三档各列一行**（读者要能对上粗细） |
    | 中心线 | ✓ 跟着 trunk 走 | 并进主干道那一行说明 |
    | 路口 | ✓ | 并进道路说明 |
    | 水系 | ✓ `water` 折线 | 有才列 |
    | 绿地 | ✓ 名字能判的 | 有才列 |
    | POI 分级 | ✓ `size` | 列一档说明（≤5 字） |
    | 等高线 / 高程点 | ✗ **没有高程数据** | **不列**（画不出也不许写） |
    | 路名 / 编号 | ✗ 没有路网表 | **不列** |

    ★ 最后两行是这次的重点：标准地图上确实有等高线和路名，**但我们没有那个数据**。
      列进图例等于承诺"图上有"，而图上没有 —— 那比不列图例更糟。
    [EN] The **city map's legend**, bottom-right, listing only elements that actually appear.
    ## Why it was needed (2026-10-26): the region map always had one, the city map **never did** --
    [EN] and the city map is exactly the one with the most symbols (blocks, three road widths,
    [EN] centre lines, junctions, green areas, graded dots), all left for the reader to guess. In the
    [EN] standard map element list a legend is the most basic item; without it the output is not a map
    [EN] but "a pile of shapes". ## What is listed: only what we have data for -- blocks, three road
    [EN] classes (one line each, so the reader can match the widths), centre line folded into the trunk
    [EN] entry, junctions folded into the road entry, water and green if present, POI grading.
    [EN] **Contours and elevation points are NOT listed** (no elevation data), and **no road names or
    [EN] numbers** (no network table). ★ That last point is the crux: standard maps do carry contours
    [EN] and road names, but **we have no such data**; listing them promises something the map does not
    [EN] show, which is worse than having no legend.
    """
    items: list[tuple] = []          # (种类, 说明, 附加参数)

    if info.get('blocks'):
        # ★★ 2026-10-26：街区那一行按**形态**说（棋盘/放射/自然生长）。
        #   三种形态切出来的块不一样，用同一句话（"按就近地标划分"）说它就是错的 ——
        #   读者会拿"就近划分"去解释一个方方正正的棋盘。
        # [EN] ★★ 2026-10-26: the block row is worded by **form** (grid / radial / organic). The
        # [EN] three forms cut differently, so one sentence ("nearest landmark") would be wrong for a
        # [EN] rectilinear grid -- the reader would try to read bisectors into right angles.
        items.append(('block', SM.NET_LABEL.get(info.get('net') or '', '街区'), None))
    # ★★★ 2026-10-27（用户：「街道图里的其他建筑呢」）：图上现在有**三层**要分开 ——
    #   地面（街区）/ 无名建筑体量 / 有名字的要地。三层都画了，图例却只解释地面，
    #   读者面对"一片浅灰小方块 + 两个深色大方块"只能猜。⇒ 各列一行。
    #   措辞必须**如实**：体量是推出来的（地块里必须有建筑才叫建成区），
    #   它没有名字、也不代表某一栋具体的房子；有名字的建筑走 `compound`。
    # [EN] ★★★ 2026-10-27 (the user: "where are the other buildings on the street map?"): the map now
    # [EN] has **three layers** to tell apart -- ground (blocks), anonymous massing, named compounds --
    # [EN] and the legend explained only the ground, leaving the reader to guess at "a field of pale
    # [EN] small rectangles plus two dark large ones". One row each. The wording must be **honest**:
    # [EN] massing is inferred (a parcel reads as built-up only if it holds buildings), it has no name
    # [EN] and stands for no particular house; anything with a name goes through `compound`.
    if info.get('compounds'):
        items.append(('compound', '要地（有名）', None))
    if info.get('massing'):
        items.append(('massing', '建筑体量（无名）', None))
    if info.get('walls'):
        # 城墙：只有 `layout.walls` 真给了折线才列（没画就不列）
        # [EN] City wall: listed only when `layout.walls` really provided a polyline
        items.append(('wall', '城墙', None))
    # ★★★ 2026-10-27：**导览模式的地物符号**要逐个列出来。
    #   导览图上一共有七八种不同的记号（方块/开口框/双横/水纹/三角/顶盖/菱形），
    #   不解释的话读者只能猜"这个三角是山还是房子"。这就是标准地图的"符号表"。
    #   ⚠ 只列**这张图上真画了的**（`info['features']` 是按实际画过的记下来的）。
    # [EN] ★★★ 2026-10-27: **guide-mode feature symbols** are listed one by one. A guide map carries
    # [EN] seven or eight distinct marks (square / open frame / double line / waves / triangle / cap /
    # [EN] diamond) and without a key the reader can only guess "is that triangle a hill or a house?" --
    # [EN] this is the standard map's symbol table. ⚠ Only what was actually drawn (`info['features']`
    # [EN] records exactly that).
    for kind, label in (info.get('features') or []):
        items.append(('feature', label, kind))
    got = set(info.get('roads') or [])
    for cls in SC.ROAD_CLASSES:      # 高 → 低，读者按"粗细递减"看下来
        if cls in got:
            items.append(('road', SC.ROAD_LABEL[cls], cls))
    if info.get('waters'):
        # 同城际图例：按类型写（河/湖/海），不写笼统的"水系"
        # [EN] Same as the region legend: word it by kind (river/lake/sea), never a blanket "water"
        items.append(('water', SM.WK_LABEL.get(info.get('water_kind') or '', '水系'), None))
    if info.get('greens'):
        items.append(('green', '绿地 / 广场', None))
    if info.get('pois') and not (info.get('features') or []):
        # ★ 导览模式下已经有**分类符号表**了，再列一条"地点（大者为要地）"是重复：
        #   那里的圆点表示"重要度"，而导览图根本没有圆点（画的是分类符号）。
        # [EN] ★ In guide mode the **symbol table** already explains the marks; adding "places (bigger =
        # [EN] more important)" would describe dots that this map does not draw.
        items.append(('poi', '地点（大者为要地）', None))
    if not items:
        return

    x0, y0, x1, y1 = span or (0.0, 0.0, float(W), float(H))
    pad, lh = 8.0, 16.0
    box_w = 176.0
    box_h = lh * len(items) + pad * 2
    bx = x1 - box_w - 10.0
    by = y1 - box_h - 10.0
    shapes.append(fcv.Rect(bx, by, box_w, box_h, border_radius=3.0,
                           paint=ft.Paint(color=_alpha(pal.get('paper', '#f8f4ea'), 0.94),
                                          style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Rect(bx, by, box_w, box_h, border_radius=3.0,
                           paint=ft.Paint(color=pal.get('link', '#c5bda9'), stroke_width=0.9,
                                          style=ft.PaintingStyle.STROKE)))
    for i, (kind, text, arg) in enumerate(items):
        cy = by + pad + lh * i + lh / 2.0
        _city_glyph(shapes, kind, bx + 18.0, cy, pal, arg)
        shapes.append(MM._text(bx + 38.0, cy - 6.5, text, size=10,
                               color=pal.get('ink', '#4a4f57'), font=font))


def _deck_legend(shapes: list, pal: dict, info: dict, *, font: str | None = None,
                 span: tuple | None = None) -> None:
    """甲板图的图例：船体 / 舱壁与舱门 / 甲板层。

    ★ 为什么甲板图需要图例：一条船体轮廓 + 几道竖壁，读者第一眼看到的是"一根香肠
      被切了几刀"。这三条记号一列，才知道那是舷侧、那是水密门、那是分几层。
    ★ 与城市/城际图同一套做法：只列**这张图上真有的**（一层就只列一层）。
    [EN] The deck plan's legend: hull, bulkheads and doors, decks. ★ Why it is needed: a hull
    [EN] outline with a few vertical cuts reads as "a sausage sliced a few times"; these three marks
    [EN] are what tell the reader "that is the side plating, that is a watertight door, that is how
    [EN] many decks". ★ Same discipline as the city and region legends: list only what is drawn.
    """
    items: list[tuple[str, str]] = [('hull', '船体（舷侧）'),
                                    ('bulkhead', '舱壁 / 舱门')]
    decks = info.get('decks') or []
    if decks:
        names = '、'.join(str(d.get('label') or '') for d in decks)
        items.append(('deck', f'分 {len(decks)} 层：{names}'))
    x0, y0, x1, y1 = span or (0.0, 0.0, float(W), float(H))
    pad, lh = 8.0, 16.0
    box_w = 176.0
    box_h = lh * len(items) + pad * 2
    bx = x1 - box_w - 10.0
    by = y1 - box_h - 10.0
    shapes.append(fcv.Rect(bx, by, box_w, box_h, border_radius=3.0,
                           paint=ft.Paint(color=_alpha(pal.get('paper', '#f8f4ea'), 0.94),
                                          style=ft.PaintingStyle.FILL)))
    shapes.append(fcv.Rect(bx, by, box_w, box_h, border_radius=3.0,
                           paint=ft.Paint(color=pal.get('link', '#c5bda9'), stroke_width=0.9,
                                          style=ft.PaintingStyle.STROKE)))
    for i, (kind, text) in enumerate(items):
        cy = by + pad + lh * i + lh / 2.0
        if kind == 'hull':
            shapes.append(fcv.Line(bx + 8.0, cy, bx + 28.0, cy,
                                   paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                                  stroke_width=4.0,
                                                  stroke_cap=ft.StrokeCap.ROUND)))
            shapes.append(fcv.Line(bx + 8.0, cy, bx + 28.0, cy,
                                   paint=ft.Paint(color=pal.get('paper', '#f8f4ea'),
                                                  stroke_width=1.8,
                                                  stroke_cap=ft.StrokeCap.ROUND)))
        elif kind == 'bulkhead':
            shapes.append(fcv.Line(bx + 18.0, cy - 7.0, bx + 18.0, cy - 2.0,
                                   paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                                  stroke_width=2.6)))
            shapes.append(fcv.Line(bx + 18.0, cy + 2.0, bx + 18.0, cy + 7.0,
                                   paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                                  stroke_width=2.6)))
            shapes.append(fcv.Line(bx + 18.0, cy + 2.0, bx + 24.0, cy - 2.0,
                                   paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                                  stroke_width=1.1)))
        shapes.append(MM._text(bx + 38.0, cy - 6.5, text, size=10,
                               color=pal.get('ink', '#4a4f57'), font=font))


def _city_glyph(shapes: list, kind: str, x: float, y: float, pal: dict,
                arg=None) -> None:
    """城市图例里的小记号 —— **与图上用同一套画法**（不是另画一个近似的）。

    ★ 这一条是硬纪律：图例记号与图上记号不一致时，读者会拿图例去对图、对不上，
      然后开始怀疑整张图（"图例里那条跟图上那条不是一回事"）。
    [EN] The small glyph in the city legend, drawn **with the same code as the map** (never a
    [EN] lookalike). ★ Hard rule: when legend and map disagree, the reader tries to match them, fails,
    [EN] and starts distrusting the whole map.
    """
    paper = pal.get('paper', '#f8f4ea')
    # ── 有名字的要地：与图上同一个画法（深填充 + 描边），只是小一号 ──
    # [EN] A named compound: the same treatment as on the map (dark fill + outline), just smaller
    if kind == 'compound':
        shapes.append(fcv.Rect(x - 8, y - 5, 16, 10, border_radius=1.0,
                               paint=ft.Paint(color=SM._mix(paper, pal.get('ink', '#4a4f57'), 0.72),
                                              style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Rect(x - 8, y - 5, 16, 10, border_radius=1.0,
                               paint=ft.Paint(color=pal.get('ink', '#4a4f57'), stroke_width=0.9,
                                              style=ft.PaintingStyle.STROKE)))
        return
    # ── 无名建筑体量：三个浅色小矩形（颜色与图上**同一档** `SM.MASS_FILL`）──
    # [EN] Anonymous massing: three pale rectangles, filled at the map's own `SM.MASS_FILL`
    if kind == 'massing':
        fill = SM._mix(paper, pal.get('ink', '#4a4f57'), SM.MASS_FILL)
        edge = SM._mix(paper, pal.get('ink', '#4a4f57'), SM.MASS_FILL + 0.20)
        for dx, w in ((-10.0, 8.0), (-1.0, 6.0), (6.0, 5.0)):
            shapes.append(fcv.Rect(x + dx, y - 5, w, 10,
                                   paint=ft.Paint(color=fill, style=ft.PaintingStyle.FILL)))
            shapes.append(fcv.Rect(x + dx, y - 5, w, 10,
                                   paint=ft.Paint(color=edge, stroke_width=0.5,
                                                  style=ft.PaintingStyle.STROKE)))
        return
    if kind == 'feature':
        # ★★★ 2026-10-27：地物符号的图例记号 **调用图上同一个函数**（`scalemap._feature_symbol`），
        #   不是另画一个长得像的。这是本文件的硬纪律：图例与图上必须同画法同尺寸，
        #   否则读者拿去对图会对不上，然后开始怀疑整张图。
        # [EN] ★★★ 2026-10-27: the feature-symbol legend mark **calls the same function as the map**
        # [EN] (`scalemap._feature_symbol`), never a lookalike. Hard rule in this file: legend and map
        # [EN] must be drawn the same way at the same size, or the reader tries to match them, fails,
        # [EN] and starts distrusting the whole map.
        SM._feature_symbol(shapes, str(arg or '屋'), x, y, 5.0, pal, here=False)
    elif kind == 'wall':
        # 城墙：与图上同一套双线（外深内浅），只是短一截
        # [EN] City wall: same double line as the map (dark outside, light inside), only shorter
        shapes.append(fcv.Line(x - 10, y, x + 10, y,
                               paint=ft.Paint(color=pal.get('ink', '#4a4f57'),
                                              stroke_width=5.0,
                                              stroke_cap=ft.StrokeCap.ROUND)))
        shapes.append(fcv.Line(x - 10, y, x + 10, y,
                               paint=ft.Paint(color=paper, stroke_width=2.4,
                                              stroke_cap=ft.StrokeCap.ROUND)))
    elif kind == 'block':
        shapes.append(fcv.Rect(x - 9, y - 6, 18, 12, border_radius=1.0,
                               paint=ft.Paint(color=_mix(paper, pal.get('wall', '#b9b1a0'), 0.10),
                                              style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Rect(x - 9, y - 6, 18, 12, border_radius=1.0,
                               paint=ft.Paint(color=_mix(paper, pal.get('ink', '#4a4f57'), 0.22),
                                              stroke_width=1.0,
                                              style=ft.PaintingStyle.STROKE)))
    elif kind == 'road':
        from image_gen import scale as _SC
        outer, inner, centre = _SC.ROAD_SPEC.get(arg or _SC.RC_LOCAL,
                                                 _SC.ROAD_SPEC[_SC.RC_LOCAL])
        # 图例里按**比例缩小**画（不然 13px 会把图例撑破），但三档的相对粗细保持不变
        # [EN] Scaled down for the legend (13px would burst the box) but the relative widths of the
        # [EN] three classes are preserved.
        k = 0.62
        shapes.append(fcv.Line(x - 10, y, x + 10, y,
                               paint=ft.Paint(color=pal.get('wall', '#b9b1a0'),
                                              stroke_width=outer * k,
                                              stroke_cap=ft.StrokeCap.ROUND,
                                              style=ft.PaintingStyle.STROKE)))
        shapes.append(fcv.Line(x - 10, y, x + 10, y,
                               paint=ft.Paint(color=paper, stroke_width=inner * k,
                                              stroke_cap=ft.StrokeCap.ROUND,
                                              style=ft.PaintingStyle.STROKE)))
        if centre:
            shapes.append(fcv.Line(x - 10, y, x + 10, y,
                                   paint=ft.Paint(color=_mix(paper, pal.get('ink', '#4a4f57'), 0.42),
                                                  stroke_width=1.0,
                                                  stroke_cap=ft.StrokeCap.ROUND,
                                                  style=ft.PaintingStyle.STROKE)))
    elif kind == 'water':
        shapes.append(fcv.Line(x - 10, y, x + 10, y,
                               paint=ft.Paint(color=pal.get('water', '#8fb0c4'),
                                              stroke_width=5.0,
                                              stroke_cap=ft.StrokeCap.ROUND,
                                              style=ft.PaintingStyle.STROKE)))
    elif kind == 'green':
        shapes.append(fcv.Circle(x, y, 6.0, paint=ft.Paint(
            color=_mix(paper, '#6f9e5a', 0.45), style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Circle(x, y, 6.0, paint=ft.Paint(
            color=_mix(paper, '#3f6e34', 0.55), stroke_width=1.0,
            style=ft.PaintingStyle.STROKE)))
    elif kind == 'poi':
        shapes.append(fcv.Circle(x - 4, y, 2.6, paint=ft.Paint(
            color=pal.get('on_paper', '#fffdf8'), style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Circle(x - 4, y, 2.0, paint=ft.Paint(
            color=pal.get('ink', '#4a4f57'), style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Circle(x + 5, y, 4.4, paint=ft.Paint(
            color=pal.get('on_paper', '#fffdf8'), style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Circle(x + 5, y, 3.6, paint=ft.Paint(
            color=pal.get('ink', '#4a4f57'), style=ft.PaintingStyle.FILL)))
