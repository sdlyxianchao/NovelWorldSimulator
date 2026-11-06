# -*- coding: utf-8 -*-
"""家具：**形状、尺寸、摆放习性**的唯一一份定义。

## 为什么单独一个模块（而不是继续写在 `floorplan._furniture` 里）

★★★ 2026-10-27（用户）：「室内图现在家具形状和摆放位置都不对 有一些都放到墙里了
家具的形状请参考一些现有标准画法绘制」。

查下来是**两个层次各错一处**，而且都源于"只有一份数据、没有一处定义"：

1. **形状**：`floorplan._furniture` 一律画 40×20 的方块 + 斜线阴影。柜台、账台小柜、
   井、灶、床、桌**全都长得一样**。井甚至被画成方块（它在 `_symbol` 里本来是同心圆，
   只因为数据里井被归成"陈设"就走了方块这条路）。
2. **尺寸与摆放**：`roomplan.FIX_PX = 15.0`，每件家具都是 15×15，
   从房间左上角 `+3px` 开始排 —— 而房间墙**向内占 4.35px**
   （`floorplan` 里两圈描边：inset 0 与 3.5、各 `stroke_width=1.7`），
   于是家具压进墙里 1.35px。这正是用户说的"放到墙里了"。

★ 这两个字都必须由**同一份表**回答："这件东西多大""它靠不靠墙"。
  两份表（摆放一份、绘制一份）必然漂 —— 演练过的坑：本项目《两处实现必然漂》。

## 画法依据（建筑制图的家具图示，不是随手画的）

平面图上家具用**轴对齐的轮廓 + 少量内部线**表示，不画立体、不画阴影：

| 家具 | 标准平面画法 | 这里 |
|------|-------------|------|
| 柜台 | 长条矩形 + 沿长边的台面分界线 | 矩形 + 中线 |
| 桌 / 案 | 矩形 + 内缩一圈（桌面边沿） | 矩形 + 内缩线 |
| 床 | 矩形 + 一端的被角折线 + 枕头 | 矩形 + 折角 + 枕块 |
| 柜 / 橱 | 矩形 + 中线 + 分格 | 矩形 + 中线 + 格线 |
| 架 / 格 | 矩形 + 数条横格 | 矩形 + 格线 |
| 灶 | 矩形 + 两个圆（锅眼） | 矩形 + 双圆 |
| 井 | **两个同心圆**（不是方块） | 同心圆 |
| 椅 / 凳 | 小方 + 一条靠背线 | 小方 + 短线 |
| 箱 / 笼 | 矩形 + 交叉对角线 | 矩形 + × |
| 其余 | 矩形轮廓 + 浅填充 | 矩形 |

★ 尺寸按"人在旁边走过"的真实比例给，不是等大方块：柜台 48×16、床 38×54、
  灶 34×22、井 直径 22、椅凳 14×14……（画布 940×600，一间房约 200×110px）。
★ **不画斜线阴影**：那是"剖面材料"的记号，不是家具。画在家具上只会让一片房间变成
  一团斜纹，看不出哪件是什么。

[EN] Furniture: the **single** definition of shape, size and placement habit.
## Why its own module (instead of living on in `floorplan._furniture`)
★★★ 2026-10-27 (the user): "the indoor furniture shapes and positions are both wrong, some are
inside the walls; draw the shapes following existing standard conventions." It turned out to be
**one fault per layer**, both caused by "one datum, no single definition": (1) **shape** -- everything
was drawn as a 40x20 block with hatch lines, so counter, cabinet, well, stove, bed and table all
looked alike; the well was even a block (it *is* drawn as concentric circles in `_symbol`, but being
classified as a "fixture" routed it down the block path). (2) **size and placement** -- `FIX_PX=15`
for everything, packed from the room's top-left `+3px`, while the wall occupies **4.35px inward**
(two stroke rings: inset 0 and 3.5, each `stroke_width=1.7`), so furniture sat 1.35px inside the
wall -- exactly the user's "inside the walls". ★ Both questions must be answered by **one table**
("how big is it" and "does it hug the wall"); two tables always drift (this project's rule).
## Drawing conventions (architectural furniture symbols, not improvised)
On a floor plan furniture is **axis-aligned outlines plus a few internal lines**: no perspective, no
shading. Counter = rectangle + centre line along its length; table = rectangle + inset ring (the
tabletop edge); bed = rectangle + turned-down corner + pillow; cabinet = rectangle + centre line +
dividers; shelf = rectangle + dividers; stove = rectangle + two circles (burners); well = **two
concentric circles** (never a block); seat = small square + a back line; chest = rectangle + an X;
everything else = outlined rectangle. ★ Sizes follow real walking clearances rather than one uniform
block: counter 48x16, bed 38x54, stove 34x22, well 22 across, stool 14x14 (canvas 940x600, a room is
about 200x110px). ★ **No hatch lines**: that is a section/material mark, not furniture -- on furniture
it just fills a room with stripes and hides what each thing is.
"""

from __future__ import annotations

from dataclasses import dataclass

#: 墙的**向内厚度**（px）。`floorplan` 画墙是两圈描边（inset 0 与 3.5、各 1.7），
#: 所以占 `0.85 + 3.5 + 0.85 = 5.2`，向内 **4.35**。
#: ★ 家具退让必须 ≥ 这个值，否则就是"家具在墙里"（实测 3.0 < 4.35）。
# ★ 这里写的是**常数**而不是从 `floorplan` 算：`roomplan` 不能 import `floorplan`
#   （方向反了，`floorplan` 已经 import `roomplan`）。改墙厚时**两处都要改**，
#   所以判据 `verify_roomplan` 会量"家具到墙的距离 ≥ 这个值"。
# [EN] The wall's **inward thickness** (px): two stroke rings (0 / 3.5, each 1.7) => 5.2 total,
# [EN] 4.35 inward. ★ Furniture must retreat at least this much (measured 3.0 < 4.35 = "inside the
# [EN] wall"). ★ It is a constant rather than derived from `floorplan` because `roomplan` must not
# [EN] import it (wrong direction; `floorplan` already imports `roomplan`). Changing the wall means
# [EN] changing both, so `verify_roomplan` measures the gap against this value.
WALL_IN = 4.35

#: 家具与墙之间再留的缝（px）：画面上看得出"东西摆在墙边"，不是嵌进墙里。
# [EN] Extra clearance between furniture and wall (px): visually "set against the wall", not in it.
WALL_GAP = 1.8

#: 家具与家具之间的缝（px）。
# [EN] Gap between two pieces of furniture (px).
ITEM_GAP = 3.0


@dataclass(frozen=True)
class FSpec:
    """一类家具：`key` 是闭集里的标识，`w`/`h` 是**默认朝向**下的宽高。

    ★★★ 2026-10-27（用户）：「不是所有家具都靠墙的 比如柜台 是要有留空站人才对
    别的家具你也要重新检查下怎么放」。⇒ 给每件家具补**摆放习性**三件套：
      · `anchor`：背靠墙(`wall`) / 贴角(`corner`) / 离墙浮置(`float`) / 居中(`center`)
      · `clear` ：需要净空的面（`front` 朝室、`back` 靠墙侧、`both` 前后、`sides` 两侧、
                  `all` 四周、`none`）
      · `clear_px`：该面的最小留白（按"人肩宽≈0.5m、站立≈0.6m"折算像素，会被房间进深 clamp）

    ★ 依据：建筑制图与室内设计平面图规范——家具分**贴墙族**与**浮置族**，浮置族
      （柜台/井/桌）四周必须留人站立或通行的净空，而不是贴着墙根堆。
    [EN] One furniture class. ★★★ 2026-10-27 (the user): "not every piece hugs a wall; a counter
    [EN] needs standing room -- re-check how the rest are placed." => each class gets a **placing habit**:
    [EN] `anchor` (wall/corner/float/center), `clear` (which side needs clearance) and `clear_px`.
    """

    key: str
    label: str
    words: tuple
    w: float
    h: float
    anchor: str = 'wall'        # 'wall' 背靠墙 | 'corner' 贴角 | 'float' 离墙浮置 | 'center' 居中
    clear: str = 'front'        # 需要净空的面: front/back/both/sides/all/none
    clear_px: float = 14.0      # 该侧需要的最小留白（站人/通行）


#: 贴墙族：背靠墙面（含贴角），用"贴墙退 pad"的排法。
# [EN] Wall-hugging classes: back against a wall (incl. corners).
ANCHOR_AGAINST = ('wall', 'corner')


def against_wall(sp: 'FSpec') -> bool:
    """这件家具属于"贴墙族"（背靠墙/贴角）吗？
        English: is this piece a wall-hugging class?"""
    return sp.anchor in ANCHOR_AGAINST


def is_float(sp: 'FSpec') -> bool:
    """这件家具属于"浮置族"（离墙/居中，四周要留净空）吗？
        English: is this piece a floating class (off-wall / centred, clearance around it)?"""
    return sp.anchor in ('float', 'center')


#: **顺序敏感**：先命中的赢。"柜台"必须排在"柜"前面，否则柜台会变成柜子。
#: ★ 这也是"同义词是字面判据的漏报后门"的落地：这里的词是**闭集**，加词要进这张表。
# [EN] **Order matters**: first hit wins, so 柜台 (counter) must precede 柜 (cabinet).
# [EN] ★ This is the project's "synonyms are a false-negative back door" rule in practice: the words
# [EN] form a closed set and new ones go into this table.
SPECS: tuple = (
    # ⚠ 尺寸在 2026-10-27 统一放大约 15%（见上文）。
    # ★ 2026-10-27 补「摆放习性」三件套（anchor / clear / clear_px）。
    #   依据：建筑制图 + 室内设计平面图的家具布置规范——家具分「贴墙族」与「浮置族」，
    #   浮置族（柜台/井/桌）四周必须留人站立或通行的净空，而不是贴着墙根。
    #   anchor: wall 背靠墙 | corner 贴角 | float 离墙浮置 | center 居中
    #   clear : 需要净空的面（front 朝室/back 靠墙侧/both 前后/sides 两侧/all 周圈/none）
    #   clear_px: 净空基准（人肩宽≈0.5m、站立≈0.6m，按图幅折算；会被房间进深 clamp）
    # [EN] Placing habit (anchor/clear/clear_px) added 2026-10-27 after the user pointed out
    # [EN] "not every piece hugs a wall; a counter needs standing room". Floor-plan convention: float
    # [EN] pieces (counter/well/table) keep clear space around them.

    # 柜台 / 吧台 / 前台 / 收银台：**浮置服务台**，前后都要留站人空间
    #   （柜台前顾客站立、柜台后店员操作）。中式铺面常沿墙但前方留走道，现代接待台为岛式；
    #   本系统取「离墙浮置」最直观表达「留空站人」。房间太窄放不下时退化为贴墙（front 仍留空）。
    # [EN] Counter: a floating service desk, standing room on both sides.
    FSpec('counter', '柜台', ('柜台', '吧台', '前台', '收银台'), 58.0, 19.0,
          anchor='float', clear='both', clear_px=26.0),

    # 井：**居中**（或离墙浮置），四周都要能取水 ⇒ 绝不可贴墙根。
    # [EN] Well: centred, reachable on all sides, never against a wall.
    FSpec('well', '井', ('井', '泉', '井台'), 26.0, 26.0,
          anchor='center', clear='all', clear_px=18.0),

    # 灶：靠墙（操作台贴墙），**灶前（操作面）留操作空间**；锅朝室内。
    # [EN] Stove: against a wall, clear working space in front (the pots face the room).
    FSpec('stove', '灶', ('灶', '炉', '锅台', '灶台'), 40.0, 26.0,
          anchor='wall', clear='front', clear_px=22.0),

    # 床 / 榻 / 炕：床头（短边）靠墙，长边两侧留上下床通道（中式床常贴一侧墙）。
    # [EN] Bed: head (short end) to the wall, clearance along the long sides.
    FSpec('bed', '床', ('床', '榻', '炕'), 44.0, 58.0,
          anchor='wall', clear='sides', clear_px=16.0),

    # 桌 / 案 / 几：居中（或离墙浮置），四周留座与通行；窄房退化为贴墙边桌。
    # [EN] Table: centred (or floating), seats and passage around it.
    FSpec('table', '桌', ('桌', '案', '几', '台案'), 36.0, 26.0,
          anchor='center', clear='sides', clear_px=20.0),

    # 架 / 格：背靠墙（书架/格架靠墙），取物侧（front）留空。
    # [EN] Shelf: back to the wall, clear in front.
    FSpec('shelf', '架', ('架', '格', '搁', '板'), 38.0, 14.0,
          anchor='wall', clear='front', clear_px=14.0),

    # 柜 / 橱 / 匣：背靠墙，开门侧（front）留空。
    # [EN] Cabinet: back to the wall, clear in front.
    FSpec('cabinet', '柜', ('柜', '橱', '匣', '箱柜'), 28.0, 21.0,
          anchor='wall', clear='front', clear_px=14.0),

    # 箱 / 笼 / 囊 / 包袱：靠墙或床尾/角落，取放侧留空。
    # [EN] Chest: by a wall or bed foot, clear on the access side.
    FSpec('chest', '箱', ('箱', '笼', '囊', '包袱'), 24.0, 19.0,
          anchor='wall', clear='front', clear_px=12.0),

    # 椅 / 凳 / 墩：靠墙或配桌，人坐的那侧朝室（front）。
    # [EN] Seat: by a wall or a table, the sitting side faces the room.
    FSpec('seat', '椅凳', ('椅', '凳', '墩', '座'), 17.0, 17.0,
          anchor='wall', clear='front', clear_px=16.0),

    # 筐 / 篓 / 篮 / 桶：靠墙角盛物（corner），取用侧留空。
    # [EN] Basket: in a corner, clear on the access side.
    FSpec('basket', '筐篓', ('筐', '篓', '篮', '桶'), 19.0, 19.0,
          anchor='corner', clear='front', clear_px=12.0),
)

#: 认不出是什么时的尺寸（按"一件家具"给，不是 15×15 的方块）
# [EN] Fallback size for an unrecognised fixture (a piece of furniture, not a 15x15 block)
DEFAULT_SPEC = FSpec('box', '陈设', (), 26.0, 19.0)

#: 类型 → spec（判据要用它核"表里有没有这一类"）
# [EN] kind -> spec (criteria use it to check the table)
BY_KEY = {sp.key: sp for sp in SPECS}


def kind_of(name: str) -> str:
    """这个名字的家具属于哪一类（闭集里的 `key`）。认不出给 `'box'`。

    ★ 用**包含**匹配而不是相等：数据里的名字是"账台小柜""靠墙的长柜台"这种带修饰的短语。
    ★ 顺序敏感（见 `SPECS` 的说明）：`柜台` 必须先于 `柜`。
    [EN] Which class this name belongs to (a `key` from the closed set); unknown gives `'box'`.
    ★ Substring matching, not equality: the data has phrases like "账台小柜". ★ Order matters.
    """
    n = str(name or '')
    if not n:
        return DEFAULT_SPEC.key
    for sp in SPECS:
        if any(k in n for k in sp.words):
            return sp.key
    return DEFAULT_SPEC.key


def spec_of(name: str) -> FSpec:
    """名字 → 这一类家具的规格（尺寸 + 靠不靠墙）。
        English: name -> the spec for its class (size + whether it hugs a wall).
    """
    return BY_KEY.get(kind_of(name), DEFAULT_SPEC)


def size_of(name: str, *, vertical: bool = False) -> tuple:
    """这件家具要占多大 `(w, h)`。`vertical=True` 表示**转过 90°**（贴左右墙时用）。

    [EN] How much room it takes, `(w, h)`; `vertical=True` means **rotated 90°** (against a side wall).
    """
    sp = spec_of(name)
    return (sp.h, sp.w) if vertical else (sp.w, sp.h)


# ══════════════════════════════════════════════════════════════════════
#  画法：每类一个记号（全部轴对齐，不画斜线阴影）
# [EN] Drawing: one symbol per class (all axis-aligned, no hatching)
# ══════════════════════════════════════════════════════════════════════
def draw(shapes: list, box: tuple, name: str, pal: dict, *,
         font: str | None = None, here: bool = False) -> None:
    """在 `box = (x0, y0, x1, y1)` 里画一件家具。

    ★ 只**按矩形画**，不自己决定位置 —— 位置由 `roomplan` 排（那边知道墙与门在哪）。
      两边各管一件事：这边管"长什么样"，那边管"摆在哪"。
    ★ 用 `fcv` 的 canvas 图元（这是一张**图**）。不要用 `ft.Container` 之类控件：
      会带进一层布局（left/top），而 flet 的 `ft.border.all` 在本机版本里不存在（实测）。
    [EN] Draw one piece of furniture inside `box = (x0, y0, x1, y1)`. ★ It only draws the shape and
    [EN] never decides the position -- `roomplan` does that (it knows where the walls and doors are).
    [EN] One job each: this side "what it looks like", that side "where it goes". ★ Use `fcv` canvas
    [EN] primitives (this is a **picture**), never controls like `ft.Container` (they drag in a layout
    [EN] layer, and `ft.border.all` does not exist in this flet build -- measured).
    """
    import flet as ft
    import flet.canvas as fcv

    x0, y0, x1, y1 = (float(v) for v in box)
    w, h = max(2.0, x1 - x0), max(2.0, y1 - y0)
    key = kind_of(name)
    edge = pal.get('wall_hi', '#6b5a44')
    fill = pal.get('furniture', '#e8ddc8')
    paper = pal.get('paper', '#f8f4ea')

    def _rect(a, b, c, d, *, fill_it=True, width=1.35, color=None):
        if fill_it:
            shapes.append(fcv.Rect(a, b, c, d, border_radius=1.0, paint=ft.Paint(
                color=fill, style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Rect(a, b, c, d, border_radius=1.0, paint=ft.Paint(
            color=color or edge, stroke_width=width, style=ft.PaintingStyle.STROKE)))

    def _line(ax, ay, bx, by, *, width=0.9, color=None):
        shapes.append(fcv.Line(ax, ay, bx, by, paint=ft.Paint(
            color=color or edge, stroke_width=width, style=ft.PaintingStyle.STROKE)))

    if key == 'well':
        # 井：**两个同心圆**（水井的老记号）。不是方块 —— 井是圆的。
        # [EN] Well: **two concentric circles** (the traditional mark). Not a block -- a well is round.
        r = min(w, h) / 2.0
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        for rr, wd in ((r, 1.6), (r * 0.52, 1.1)):
            shapes.append(fcv.Circle(cx, cy, rr, paint=ft.Paint(
                color=edge, stroke_width=wd, style=ft.PaintingStyle.STROKE)))

    elif key == 'stove':
        # 灶：矩形 + 两个圆（锅眼）。圆是**锅**，所以不填色（填了像两口黑锅盖）。
        # [EN] Stove: rectangle + two circles (burners), unfilled so they read as pots, not black lids.
        _rect(x0, y0, w, h)
        r = min(h * 0.30, w * 0.22)
        for fx in (x0 + w * 0.30, x0 + w * 0.70):
            shapes.append(fcv.Circle(fx, y0 + h / 2.0, r, paint=ft.Paint(
                color=edge, stroke_width=1.0, style=ft.PaintingStyle.STROKE)))

    elif key == 'bed':
        # 床：矩形 + 一头 22% 处的折角（被角）+ 靠里那一头的枕头块
        # [EN] Bed: rectangle + a folded corner at 22% + a pillow block at the far end
        _rect(x0, y0, w, h)
        if h >= w:
            fold = y0 + h * 0.22
            _line(x0, fold, x0 + w * 0.42, fold, width=1.0)
            _line(x0 + w * 0.42, fold, x0 + w * 0.42, y0, width=1.0)
            pw, ph = w * 0.62, h * 0.10
            shapes.append(fcv.Rect(x0 + (w - pw) / 2.0, y0 + h * 0.05, pw, ph,
                                   border_radius=2.0, paint=ft.Paint(
                                       color=paper, stroke_width=0.9,
                                       style=ft.PaintingStyle.STROKE)))
        else:
            fold = x0 + w * 0.22
            _line(fold, y0, fold, y0 + h * 0.42, width=1.0)
            _line(fold, y0 + h * 0.42, x0, y0 + h * 0.42, width=1.0)
            pw, ph = w * 0.10, h * 0.62
            shapes.append(fcv.Rect(x0 + w * 0.05, y0 + (h - ph) / 2.0, pw, ph,
                                   border_radius=2.0, paint=ft.Paint(
                                       color=paper, stroke_width=0.9,
                                       style=ft.PaintingStyle.STROKE)))

    elif key == 'counter':
        # 柜台：长条 + 沿长边一条**台面分界线**（柜台面比柜体窄一档）
        # [EN] Counter: a long band + one **top-edge line** along its length
        _rect(x0, y0, w, h)
        if w >= h:
            _line(x0 + 1.0, y0 + h * 0.42, x1 - 1.0, y0 + h * 0.42, width=0.9)
        else:
            _line(x0 + w * 0.42, y0 + 1.0, x0 + w * 0.42, y1 - 1.0, width=0.9)

    elif key == 'table':
        # 桌 / 案：矩形 + **内缩一圈**（桌面边沿）
        # [EN] Table: rectangle + an **inset ring** (the tabletop edge)
        _rect(x0, y0, w, h)
        ins = min(3.2, w * 0.16, h * 0.16)
        shapes.append(fcv.Rect(x0 + ins, y0 + ins, w - 2 * ins, h - 2 * ins,
                               border_radius=1.0, paint=ft.Paint(
                                   color=edge, stroke_width=0.8,
                                   style=ft.PaintingStyle.STROKE)))

    elif key == 'cabinet':
        # 柜：矩形 + 中线 + 一条分格
        # [EN] Cabinet: rectangle + centre line + one divider
        _rect(x0, y0, w, h)
        if w >= h:
            _line(x0, y0 + h / 2.0, x1, y0 + h / 2.0, width=0.8)
            if w > 26:
                _line(x0 + w / 2.0, y0, x0 + w / 2.0, y1, width=0.8)
        else:
            _line(x0 + w / 2.0, y0, x0 + w / 2.0, y1, width=0.8)
            if h > 26:
                _line(x0, y0 + h / 2.0, x1, y0 + h / 2.0, width=0.8)

    elif key == 'shelf':
        # 架 / 格：矩形 + 数条横格（架子是分层的）
        # [EN] Shelf: rectangle + several dividers (a shelf has tiers)
        _rect(x0, y0, w, h, fill_it=False)
        n = 3 if (w if w >= h else h) > 24 else 2
        for i in range(1, n + 1):
            if w >= h:
                yy = y0 + h * i / (n + 1)
                _line(x0, yy, x1, yy, width=0.7)
            else:
                xx = x0 + w * i / (n + 1)
                _line(xx, y0, xx, y1, width=0.7)

    elif key == 'chest':
        # 箱 / 笼：矩形 + 交叉对角线
        # [EN] Chest: rectangle + an X
        _rect(x0, y0, w, h)
        _line(x0 + 1, y0 + 1, x1 - 1, y1 - 1, width=0.7)
        _line(x1 - 1, y0 + 1, x0 + 1, y1 - 1, width=0.7)

    elif key == 'seat':
        # 椅 / 凳：小方 + 一条靠背线（靠背在长边那一侧）
        # [EN] Seat: a small square + one back line (on the long side)
        _rect(x0, y0, w, h)
        if w >= h:
            _line(x0 + 1.0, y0 + 1.0, x1 - 1.0, y0 + 1.0, width=2.0)
        else:
            _line(x0 + 1.0, y0 + 1.0, x0 + 1.0, y1 - 1.0, width=2.0)

    elif key == 'basket':
        # 筐篓：圆 + 一条弦（编织的开口）
        # [EN] Basket: a circle + one chord (the open top)
        r = min(w, h) / 2.0
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        shapes.append(fcv.Circle(cx, cy, r, paint=ft.Paint(
            color=fill, style=ft.PaintingStyle.FILL)))
        shapes.append(fcv.Circle(cx, cy, r, paint=ft.Paint(
            color=edge, stroke_width=1.0, style=ft.PaintingStyle.STROKE)))
        _line(cx - r * 0.7, cy, cx + r * 0.7, cy, width=0.7)

    else:
        # 其余：矩形轮廓 + 浅填充（**不画斜线**：那是剖面材料记号）
        # [EN] Everything else: an outlined rectangle with a light fill (**no hatch**: that is a
        # [EN] section/material mark)
        _rect(x0, y0, w, h)

    if here:
        shapes.append(fcv.Rect(x0 - 1.5, y0 - 1.5, w + 3.0, h + 3.0, border_radius=2.0,
                               paint=ft.Paint(color=pal.get('here', '#b23028'),
                                              stroke_width=1.8,
                                              style=ft.PaintingStyle.STROKE)))
