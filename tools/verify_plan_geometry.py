# -*- coding: utf-8 -*-
"""验证：地图的**几何**（家具在房间内 · 院子不压房子 · 图例无框不溢出 · 比例尺在图例下面 · 名字贴墙）
＋ 美术的 **Reflection 环**（画完自审 · 有问题自修 · 再审到通过）。

用户 2026-10-12 原话（七件事，逐条对应到下面的分组）
----------------------------------------------
    「还一个问题 这个大地图 **柜台跑到墙外面了**」
    「左上角的图例 **有些字在方框外面**」
    「还有**比例尺把字盖住了** **比例尺你放到左下角吧**」
    「还有左上角的图例 **不要带方框了** 但是要注意**地图部分不要跟图例重合**」
    「房子和院子都是正方形 这没问题 但是**房子的一部分和院子的一部分重合里**
      **美术Agent绘制地图的时候要用Reflection的机制 绘制之后去审核
      如果有问题则修复问题重新绘制 直到没问题**」
    「还有大地图右上角**2 个关闭按钮** **留外面的一个就行 红底的关闭按钮去掉**」
    「还一个 不管是大地图还是小地图 **建筑的名字标记都放到墙的旁边**
      **不要放到别的东西的上面**」

判据分七组
----------
  A **审核器查得出来**：注入四种问题，`audit_layout()` / `audit()` 都报得出来
     （**只读** —— 审核不改任何东西）
  B **修复真的修好**（★★★ 这一组是 Reflection 的核心）：修完**再审必须是干净的**；
     而且是**行为级**的（不看源码，直接跑一遍修 + 审）
  C **渲染层几何**：解算出来的陈设**在它那间房里**；院子与房子**不重叠**；
     **画出来的形状**也要落在房间里（解算对了但没照着画 = 一样是 bug）
  D **只加不减**：修复不删任何地点（删了 = 那一处从图上消失）
  E **图例与比例尺**：图例**没有方框**；图例文字**不溢出**；比例尺**接在图例最后一条之下**
     （★ 2026-10-24 用户推翻了 10-12 的"放左下角"：「大地图比例尺又被挡住了
     请把比例尺后续就放到图例的下面」）
  F **只有一个关闭按钮**：画出的大地图上**不许再有**那个叠在图上的关闭按钮
  G **名字贴墙**：房间名 / 院子名 / 建筑名都**紧贴现线**（不是飘在中间）
  H **美术挂了 Reflection**：`day_layout` 的**方法体里真的调了** `reflect_layout`
     （AST 判 —— 写了没人调等于没做）

跑法：
    .venv\\Scripts\\python.exe tools/verify_plan_geometry.py
产出：assets/screenshots/plan_geometry_report.json

English:
Verification: the map's **geometry** (furniture inside its room · courtyard not pressing on the house
· legend has no box and does not overflow · scale bar bottom-left · names hug the wall) plus the art
dept's **Reflection loop** (audit after drawing · self-repair · audit again until clean).

The user's exact words on 2026-10-12 (seven items, each mapped to a group below)
----------------------------------------------
    "another problem: on this big map **the counter has run outside the wall**"
    "in the top-left legend **some text is outside the box**"
    "and **the scale bar covers the text** -- **put the scale bar in the bottom-left**"
    "and the top-left legend **should not have a box**, but note that **the map part must not overlap
     the legend**"
    "the house and the courtyard are both squares, that's fine, but **part of the house and part of
     the courtyard overlap**; **when the art Agent draws the map it should use the Reflection
     mechanism: after drawing, go and audit it; if there is a problem, fix it, redraw, until there is
     no problem**"
    "and there are **2 close buttons in the big map's top-right**; **keep just the outer one --
     remove the red-background one**"
    "one more: whether it's the big map or the minimap, **put the building's name label beside the
     wall**, **not on top of other things**"

Criteria are in seven groups
----------
  A **the auditor can find it**: inject four kinds of problem; both `audit_layout()` and `audit()`
    report them (**read-only** -- auditing changes nothing)
  B **the repair really fixes them** (★★★ the heart of Reflection): after repairing, **re-auditing
    must be clean**; and it is **behavioural** (run repair + audit, do not read the source)
  C **render-layer geometry**: a solved fixture is **inside its room**; the courtyard and the house
    **do not overlap**; **the shapes actually drawn** must also land inside the room (solved right but
    not drawn so = a bug just the same)
  D **only add, never remove**: a repair deletes no location (deleting = that spot vanishes from the
    map)
  E **legend and scale bar**: the legend has **no box**; legend text **does not overflow**; the scale
    bar is in the **bottom-left**
  F **only one close button**: the drawn big map must **not** carry that overlaid close button again
  G **names hug a wall**: room name / courtyard name / building name all **hug a wall line** (not
    floating in the middle)
  H **the art dept is wired to Reflection**: `day_layout`'s **method body really calls**
    `reflect_layout` (AST check -- written but never called equals not done)
Usage:
    .venv\\Scripts\\python.exe tools\\verify_plan_geometry.py
Output: assets/screenshots/plan_geometry_report.json
"""
from __future__ import annotations

import ast
import json
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import flet.canvas as fcv                               # noqa: E402
import verify_ui_common as VU                           # noqa: E402
VU.redirect_env_writes()

from image_gen import floorplan as FP                   # noqa: E402
from image_gen import minimap as MM                     # noqa: E402
from image_gen import plan_audit as PA                  # noqa: E402
from image_gen.map_layout import Layout, Place          # noqa: E402
from i18n import set_lang                               # noqa: E402

set_lang('zh')
OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

#: 用户截图里那种（茶馆：屋里几间 + 院子里的井 + 门）。**每一组都用它**。
# [EN] : the kind in the user's screenshot (teahouse: rooms + a well in the yard + the gate). **Every
# [EN] group uses it.**
def tea_house() -> Layout:
    return Layout(places=[Place('门', 0.5, 0.88, shape='门'),
                          Place('堂屋', 0.32, 0.56, shape='屋'),
                          Place('柜台', 0.68, 0.56),
                          Place('天井', 0.5, 0.40, shape='院'),
                          Place('井', 0.28, 0.30, shape='院'),
                          Place('后院', 0.5, 0.16, shape='院')],
                  kind='室内', frame='临河茶肆', caption='临河茶肆')


def _shapes(lay=None, **kw) -> list:
    return FP.build_detail_shapes(lay or tea_house(),
                                  place='临河茶肆', when='第 3 天 · 戌时', **kw)


def _rects(shapes: list) -> list:
    return [(float(r.x), float(r.y), float(r.x) + float(r.width),
             float(r.y) + float(r.height))
            for r in shapes if isinstance(r, fcv.Rect)]


def _texts(shapes: list) -> list:
    """`(文字, x, y, 字号)` —— ⚠ 字号在 `style.size` 里（`Text` 自己没有）。
    [EN] `(text, x, y, font size)` -- ⚠ the size lives in `style.size`."""
    out = []
    for s in shapes:
        if type(s).__name__ != 'Text':
            continue
        st = getattr(s, 'style', None)
        out.append((str(getattr(s, 'value', '')), float(getattr(s, 'x', 0) or 0),
                    float(getattr(s, 'y', 0) or 0),
                    float(getattr(st, 'size', 0) or 0)))
    return out


def _solve(lay=None, *, current: str = '堂屋', name_band: bool = True):
    lay = lay or tea_house()
    detail = MM.detail_of(lay)
    # ★ 与 `_shapes()`（`build_detail_shapes`）**同一份 name_band**，否则
    #   `plan.house` 的顶墙位置和画出来的楼名带对不上，G2 这类判据会假红。
    # [EN] ★ Same `name_band` as `_shapes()` so `plan.house`'s top wall matches the drawn name
    # [EN] band; otherwise G2-style checks go falsely red.
    return PA.solve(lay, px=FP.layout_px(FP.W, FP.H, detail),
                    span=FP.layout_span(FP.W, FP.H, detail),
                    detail=detail, current=current, grow=FP.PLAN_GROW,
                    name_band=FP.NAME_BAND if name_band else 0.0), detail


report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  A. 审核器查得出来（且**只读**）
# [EN] A. The auditor can find it (and is **read-only**)
# ══════════════════════════════════════════════════════════════════
def test_audit_finds() -> None:
    # ① 陈设没有房间可放
    #    ⚠ 夹具要用**真正的陈设**（柜台 / 条案 / 灶）—— `井` 是**户外器物**，
    #      它报的是"没有院子"那条（第一版拿井当夹具，判据因此假红）。
    # [EN] (1) A fixture with no room to go in.
    # [EN]   ⚠ The fixture must be a **real fixture** (counter / side table / stove) -- `井` is an
    # [EN]   **outdoor object** and triggers the "no courtyard" rule instead (the first version used a
    # [EN]   well as the fixture, so this criterion went falsely red).
    lay = Layout(places=[Place('柜台', 0.3, 0.3), Place('条案', 0.7, 0.6)], kind='局部')
    found = PA.audit_layout(lay)
    ok('A1 ★★ 审核查得出「陈设没有可放进去的房间」'
       '—— 那它在渲染时只能落到"没有墙"的地方 = 用户看到的"跑到墙外"',
       sum(1 for i in found if i.kind == PA.K_FURN_ORPHAN) >= 1,
       str([i.kind for i in found]))

    # ② 有见的天的东西却没院子
    # [EN] (2) A sky-open object but no courtyard
    lay2 = Layout(places=[Place('堂屋', 0.5, 0.7, shape='屋'),
                          Place('井', 0.3, 0.3)], kind='室内')
    found2 = PA.audit_layout(lay2)
    ok('A2 ★★ 审核查得出「有见天的东西却没有院子」'
       '（用户点名的硬规则：出现井就必须有院子）',
       any(i.kind == PA.K_YARD_MISSING for i in found2),
       str([i.kind for i in found2]))

    # ③ 房子与院子在**布局上**就必然相撞
    # [EN] (3) House and courtyard **bound to collide in the layout**
    lay3 = Layout(places=[Place('堂屋', 0.5, 0.6, shape='屋'), Place('柜台', 0.5, 0.6),
                          Place('井', 0.48, 0.62), Place('后院', 0.5, 0.58)],
                  kind='室内')
    found3 = PA.audit_layout(lay3)
    ok('A3 ★★★ 审核查得出「院子与房子重叠」（用户报的那个）',
       any(i.kind == PA.K_YARD_OVERLAP for i in found3),
       str([i.kind for i in found3]))

    # ④ 渲染层：把一份"院子压着房子"的布局画出来，`audit()` 必须报
    #    ⚠ 渲染层的 `solve()` 会**主动推开**它们 —— 所以这里查的是"解算之后不重叠"
    #      （那正是 `solve()` 的职责）；`audit()` 报不报，取决于解算结果。
    # [EN] (4) Render layer: draw a layout where "the courtyard presses on the house" and `audit()`
    # [EN]   must report it.
    # [EN]   ⚠ The render layer's `solve()` **pushes them apart** on its own -- so what is checked
    # [EN]   here is "no overlap after solving" (that is `solve()`'s job); whether `audit()` reports
    # [EN]   depends on the solved result.
    plan, _d = _solve(lay3)
    ok('A4 ★★★ 渲染层的 `audit()` 也报同一件事（解算之后仍重叠就报）'
       '—— 与布局层**用同一个问题名**，"修没修好"看的是同一个词',
       (PA.overlap_area(plan.yard, plan.house) <= 1.0)
       or any(i.kind == PA.K_YARD_OVERLAP for i in PA.audit(plan)),
       f'重叠 {round(PA.overlap_area(plan.yard, plan.house))}')

    # ⑤ **只读**：审核不许改任何东西
    #    ⚠⚠ **必须用自己新建的夹具**（2026-10-12 反例法当场抓到）：
    #      第一版复用了上面 `lay3`，而 `lay3` 已经被第 ③ 步的 `audit_layout(lay3)`
    #      **读过一次**了 —— 万一审核改了它，`before` 记的就是**改过之后**的值，
    #      于是"前后一样"恒成立，判据**永远绿**（变异抓不到，实测报了"没抓到"）。
    #      判据之间**共用会被改的夹具**是这一类的根源：这条判据要验的正是"会不会被改"。
    # [EN] (5) **Read-only**: auditing must change nothing.
    # [EN]   ⚠⚠ It **must use its own fresh fixture** (the counterexample method caught this on
    # [EN]   2026-10-12): the first version reused `lay3` above, which step (3) had **already read
    # [EN]   once** -- if auditing changed it, `before` recorded the **already-changed** values, making
    # [EN]   "before equals after" always true and the criterion **permanently green** (the mutation was
    # [EN]   not caught; measured as "not caught"). Criteria sharing a fixture that can be mutated is
    # [EN]   the root of this class -- and what this criterion checks is precisely "can it be mutated".
    lay5 = Layout(places=[Place('堂屋', 0.5, 0.6, shape='屋'),
                          Place('柜台', 0.5, 0.6),
                          Place('井', 0.48, 0.62),
                          Place('后院', 0.5, 0.58)], kind='室内')
    before = [(p.name, p.x, p.y) for p in lay5.places]
    PA.audit_layout(lay5)
    plan5, _d5 = _solve(lay5)
    PA.audit(plan5)
    after = [(p.name, p.x, p.y) for p in lay5.places]
    ok('A5 ★★ 审核是**只读**的（跑完两遍审核，地点的坐标一个都没动）'
       '—— "查"与"修"分开，"审核报告"才可信',
       before == after, f'{before} vs {after}')


# ══════════════════════════════════════════════════════════════════
#  B. 修复真的修好（★★★ Reflection 的核心）
# [EN] B. The repair really fixes it (★★★ the heart of Reflection)
# ══════════════════════════════════════════════════════════════════
def test_repair() -> None:
    cases = [
        ('陈设没房间', Layout(places=[Place('井', 0.7, 0.6),
                                      Place('柜台', 0.3, 0.3)], kind='局部')),
        ('有井没院子', Layout(places=[Place('堂屋', 0.5, 0.7, shape='屋'),
                                      Place('井', 0.3, 0.3)], kind='室内')),
        ('房子压院子', Layout(places=[Place('堂屋', 0.5, 0.6, shape='屋'),
                                      Place('柜台', 0.5, 0.6),
                                      Place('井', 0.48, 0.62),
                                      Place('后院', 0.5, 0.58)], kind='室内')),
    ]
    for tag, lay in cases:
        before = PA.audit_layout(lay)
        fixed, _iss = PA.reflect_layout(lay)
        after = PA.audit_layout(fixed)
        ok(f'B ★★★ Reflection：**{tag}** 修完**再审是干净的**'
           f'（修前 {len(before)} 处 → 修后 {len(after)} 处）'
           '—— 这就是用户要的"如果有问题则修复问题重新绘制 直到没问题"',
           bool(before) and not after,
           f'修前 {[i.kind for i in before]} · 修后 {[i.kind for i in after]}')

    # ★★ 修完的布局**画出来也不许有几何错**（两层一起过才算"没问题"）
    # [EN] ★★ The repaired layout must **also draw without geometry errors** (both layers clean is
    # [EN] what "no problem" means)
    lay = Layout(places=[Place('堂屋', 0.5, 0.6, shape='屋'), Place('柜台', 0.5, 0.6),
                         Place('井', 0.48, 0.62), Place('后院', 0.5, 0.58)],
                 kind='室内', frame='临河茶肆')
    fixed, _ = PA.reflect_layout(lay)
    plan, _d = _solve(fixed, current='堂屋')
    bad_furn = []
    for name, (owner, pos) in plan.fixtures.items():
        rb = plan.rooms.get(owner)
        if rb is None or not PA.contains((pos[0] - 20, pos[1] - 10,
                                          pos[0] + 20, pos[1] + 10), rb.box, tol=1.0):
            bad_furn.append(name)
    ok('B5 ★★★ 修完的布局**画出来也对**：陈设落在房间里、院子与房子不重叠'
       '—— 布局层与渲染层**两层都干净**才算"没问题"',
       not bad_furn and PA.overlap_area(plan.yard, plan.house) <= 1.0
       and bool(plan.fixtures) and bool(plan.rooms),
       f'家具 {bad_furn} · 重叠 {round(PA.overlap_area(plan.yard, plan.house))}')


# ══════════════════════════════════════════════════════════════════
#  C. 渲染层几何
# [EN] C. Render-layer geometry
# ══════════════════════════════════════════════════════════════════
def test_render_geometry() -> None:
    plan, detail = _solve()
    ok('C1 ★★★ 解算给出了房间与院子（不是空跑 —— 判据自己在验自己）',
       bool(plan.rooms) and plan.yard is not None and plan.house is not None,
       f'房间 {list(plan.rooms)} · 院子 {plan.yard is not None}')

    # ① 陈设落在它那间房里（**用户报的"柜台跑到墙外面"**）
    # [EN] (1) The fixture lands inside its room (**the user's "the counter ran outside the wall"**)
    bad = []
    for name, (owner, pos) in plan.fixtures.items():
        rb = plan.rooms.get(owner)
        if rb is None:
            bad.append(f'{name}:归属「{owner}」不是房间')
            continue
        box = (pos[0] - 20, pos[1] - 10, pos[0] + 20, pos[1] + 10)
        if not PA.contains(box, rb.box, tol=1.0):
            bad.append(f'{name}:{tuple(round(v) for v in box)} 不在 {PA._r(rb.box)}')
    ok('C2 ★★★ 陈设**落在它所属的那间房里**（用户：「柜台跑到墙外面了」）'
       '—— 归属优先用布局里写的 `房间`，没写就按几何最近的一间兜底',
       bool(plan.fixtures) and not bad, str(bad or list(plan.fixtures)))

    # ② 院子与房子不重叠
    #    ⚠⚠ **必须先要求"院子真的存在"**（2026-10-12 反例法当场抓到）：
    #      第一版只写 `ov <= 1.0` —— 把院子整去掉（`yard = None`）时
    #      `overlap_area(None, house)` 返回 0，"不重叠"**照样成立** ⇒ 判据绿。
    #      "没有院子"和"院子不压房子"是两件事，前者是**更严重**的错。
    # [EN] (2) Courtyard and house do not overlap.
    # [EN]   ⚠⚠ It **must first require the courtyard to exist** (caught by the counterexample method
    # [EN]   on 2026-10-12): the first version only wrote `ov <= 1.0` -- removing the courtyard
    # [EN]   entirely (`yard = None`) makes `overlap_area(None, house)` return 0, so "no overlap"
    # [EN]   **still holds** and the criterion stays green. "No courtyard" and "the courtyard does not
    # [EN]   press on the house" are two different things, and the former is the **worse** error.
    ov = PA.overlap_area(plan.yard, plan.house)
    ok('C3 ★★★ 院子与房子**不重叠**（用户：「房子的一部分和院子的一部分重合里」）'
       '—— ⚠ 还得**有院子**：没有院子时"不重叠"是假的（那是更严重的错）',
       plan.yard is not None and plan.house is not None and ov <= 1.0,
       f'院子 {PA._r(plan.yard)} · 重叠 {round(ov)} px²')

    # ③ **画出来的形状**也要对（解算对了但没照着画 = 一样是 bug）
    # [EN] (3) **The shapes actually drawn** must be right too
    shapes = _shapes()
    # ⚠ 2026-10-27：**不能再按"40×20"认家具** —— 那个尺寸就是"家具全一样大"的病根
    #   （用户：「家具形状和摆放位置都不对」）。现在尺寸按类型给（柜台 48×16、床 38×54、
    #   井 直径 22…），所以"这件是不是家具"改按 **`furniture` 表里的尺寸集合** 认。
    #   ★ 判据要跟着**产品现在的定义**走，不能钉死某一版的具体数值 —— 钉数值的判据
    #     在改对之后必然红，而下一个人会去改判据（而不是发现产品变好了）。
    # [EN] ⚠ 2026-10-27: **no longer recognise furniture by "40x20"** -- that size was the root of
    # [EN] "all furniture is the same size" (the user: "the shapes and positions are both wrong").
    # [EN] Sizes are now per class (counter 48x16, bed 38x54, well 22 across), so "is this a piece of
    # [EN] furniture" is decided by membership in the **`furniture` table's size set**. ★ A criterion
    # [EN] must follow the product's **current** definition, never pin one version's numbers: a pinned
    # [EN] value goes red precisely after the fix, and the next person edits the criterion instead of
    # [EN] noticing the product improved.
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from image_gen import furniture as _FR
    _fsizes = set()
    for _sp in tuple(_FR.SPECS) + (_FR.DEFAULT_SPEC,):
        _fsizes.add((round(_sp.w, 1), round(_sp.h, 1)))
        _fsizes.add((round(_sp.h, 1), round(_sp.w, 1)))
    furn = [b for b in _rects(shapes)
            if (round(b[2] - b[0], 1), round(b[3] - b[1], 1)) in _fsizes]
    drawn_ok = [b for b in furn
                if any(PA.contains(b, rb.box, tol=1.0) for rb in plan.rooms.values())]
    ok('C4 ★★★ **画在画布上的**家具**全部在房间里**'
       '（反例法抓到过"只测函数、没测渲染真的用了它"）',
       bool(furn) and len(drawn_ok) == len(furn),
       f'{len(drawn_ok)}/{len(furn)} 在房间里 · 认到的尺寸 '
       f'{sorted({(round(b[2] - b[0]), round(b[3] - b[1])) for b in furn})[:6]}')

    # ④ 房间矩形都在绘图区内（跑到图例区里就是"地图与图例重合"）
    # [EN] (4) Room rectangles are inside the drawing area (straying into the legend area is "the map
    # [EN] overlapping the legend")
    span = FP.layout_span(FP.W, FP.H, detail)
    out = [n for n, r in plan.rooms.items() if not PA.contains(r.box, span, tol=1.0)]
    ok('C5 ★★ 房间矩形都在**绘图区内**（不许伸进图例那一带）',
       not out, str(out))
    report['plan'] = {'rooms': {k: PA._r(v.box) for k, v in plan.rooms.items()},
                      'yard': PA._r(plan.yard), 'house': PA._r(plan.house),
                      'overlap': round(ov)}


# ══════════════════════════════════════════════════════════════════
#  D. 只加不减
# [EN] D. Only add, never remove
# ══════════════════════════════════════════════════════════════════
def test_additive() -> None:
    for tag, lay in (
        ('陈设没房间', Layout(places=[Place('井', 0.7, 0.6),
                                      Place('柜台', 0.3, 0.3)], kind='局部')),
        ('有井没院子', Layout(places=[Place('堂屋', 0.5, 0.7, shape='屋'),
                                      Place('井', 0.3, 0.3)], kind='室内')),
        ('房子压院子', Layout(places=[Place('堂屋', 0.5, 0.6, shape='屋'),
                                      Place('柜台', 0.5, 0.6),
                                      Place('井', 0.48, 0.62),
                                      Place('后院', 0.5, 0.58)], kind='室内')),
    ):
        was = {p.name for p in lay.places}
        fixed, _ = PA.reflect_layout(lay)
        now = {p.name for p in fixed.places}
        ok(f'D ★★ **{tag}** 修复**只加不减**（原来的地点一个都没少）'
           '—— 删了就等于"这一处从图上消失了"',
           was <= now, f'少了 {sorted(was - now)}')


# ══════════════════════════════════════════════════════════════════
#  E. 图例与比例尺
# [EN] E. Legend and scale bar
# ══════════════════════════════════════════════════════════════════
def test_legend() -> None:
    shapes = _shapes()
    detail = MM.detail_of(tea_house())

    # ① 图例**没有方框**（用户：「左上角的图例 不要带方框了」）
    #    ⚠ 判法：`_info_box` 原来画两个 268×148 的矩形（底色 + 边框）——
    #      现在一个都不该有。
    # [EN] (1) The legend has **no box** (the user: "the top-left legend should not have a box").
    # [EN]   How: `_info_box` used to draw two 268x148 rectangles (fill + stroke) -- now none.
    box = [b for b in _rects(shapes)
           if abs((b[2] - b[0]) - FP.INFO_W) < 3
           and abs((b[3] - b[1]) - FP.INFO_H) < 3]
    ok('E1 ★★★ 图例**没有方框**（268×148 那个矩形一个都不剩）'
       '—— 用户：「左上角的图例 不要带方框了」',
       not box, f'还剩 {len(box)} 个：{[tuple(round(v) for v in b) for b in box[:2]]}')

    # ② 图例文字**不溢出**（用户：「有些字在方框外面」）
    # [EN] (2) Legend text **does not overflow** (the user: "some text is outside the box")
    LH = FP.legend_height(detail)
    leg = [(v, x, y, s) for v, x, y, s in _texts(shapes)
           if x < FP.INFO_W + 40 and y < LH + 12]
    over = [(v, round(x + MM._cjk_w(v, s))) for v, x, y, s in leg
            if x + MM._cjk_w(v, s) > FP.INFO_W or y > LH]
    ok('E2 ★★★ 图例文字**一行都不溢出**（右边界与下边界都在"图例实高"之内）'
       '—— 用户：「有些字在方框外面」。'
       '⚠ 高度是**按条目数算出来的**（`legend_height()`），不是写死的 148',
       bool(leg) and not over,
       f'{len(leg)} 行 · 溢出 {over} · 实高 {LH:.0f}')

    # ③ 比例尺在**图例下面**
    # ★★★ 2026-10-24 改口径（用户推翻了 2026-10-12 那个设计）：
    #   原话「**大地图比例尺又被挡住了** 请把比例尺后续就放到**图例的下面**」。
    #   左下角那一带是地图内容的下沿，画在那儿谁都会看成"被挡住"（10-22 修过一次底纹，
    #   这次用户又看到了）⇒ 现在的守点不是"在左下角"，而是"**接在图例最后一条之下**"。
    # [EN] (3) The scale bar sits **below the legend**.
    # [EN] ★★★ Re-specified 2026-10-24 (the user overturned the 2026-10-12 design): "**the big map's
    # [EN] scale bar is covered again** -- from now on put it **below the legend**". The bottom-left is
    # [EN] the map content's lower edge, so anything drawn there reads as "covered" (we fixed the grid
    # [EN] once on 10-22 and the user saw it again); the criterion now guards "**right below the last
    # [EN] legend entry**", not "bottom-left".
    #  ⚠ 只判"在左列 + 在图例文字之下"是**不够的** —— 画布左下角那一整条也满足
    #    这两个条件（实测反例法当场漏掉：把比例尺搬回 (18,566)，判据照样绿）。
    #    所以还要判**紧邻**：标题顶离图例最后一条不超过 `_NEAR`。
    #    实测（正常）23px、`_NEAR=40` ⇒ 1.7 倍余量；搬回底部时是 375px，一眼分开。
    # [EN] ⚠ "In the left column + below the legend text" is **not enough** -- the whole column
    # [EN] down the canvas' bottom-left also satisfies both (the counterexample method caught it
    # [EN] immediately: move the scale bar back to (18, 566) and the criterion stayed green). So it
    # [EN] must also be **adjacent**: the title's top is within `_NEAR` of the last legend entry.
    # [EN] Measured (normal) 23px with `_NEAR=40` => 1.7x margin; down at the bottom it is 375px.
    _NEAR = 40.0
    sb = [(v, x, y) for v, x, y, s in _texts(shapes) if '比例尺' in v]
    leg_bottom = FP.legend_text_bottom(detail)
    in_leg_col = bool(sb) and all(
        x < FP.INFO_W and leg_bottom <= y <= leg_bottom + _NEAR for _v, x, y in sb)
    ok('E3 ★★★ 比例尺**接在图例最后一条之下**（左上角那一列，不是左下角）'
       '—— 用户 2026-10-24：「大地图比例尺又被挡住了 请把比例尺后续就放到图例的下面」'
       '（推翻了 10-12 的"放左下角"）',
       in_leg_col, f'图例文字底={leg_bottom:.0f} · '
                   + str([(v, round(x), round(y)) for v, x, y in sb]))

    # ④ 比例尺**不压图例条目**（两个的矩形不许重叠）
    # [EN] (4) The scale bar must **not press on the legend entries**
    #  ⚠ 图例条目只取 `legend_text_bottom()` **之上**的那些行 —— 比例尺自己的标题也
    #    含"比例尺"三个字、也落在左上角，不过滤就会"自己跟自己重叠"假红。
    # [EN] ⚠ Only rows **above** `legend_text_bottom()` count as legend entries -- the scale bar's own
    # [EN] title contains "比例尺" too and also sits in the top-left, so without this filter the
    # [EN] criterion goes red on "the scale bar overlaps itself".
    leg = [(v, x, y, s) for v, x, y, s in _texts(shapes)
           if x < FP.INFO_W and y < leg_bottom]
    ov = False
    for _v, x, y in sb:
        cell = (x, y - 13, x + FP.SCALE_CELLS * FP.SCALE_CELL_W, y + 12)
        for _t, lx, ly, ls in leg:
            lbox = (lx, ly, lx + MM._cjk_w(_t, ls), ly + ls + 3)
            if PA.overlap_area(cell, lbox) > 0:
                ov = True
    ok('E4 ★★ 比例尺与图例**不重叠**（用户：「比例尺把字盖住了」）',
       bool(sb) and not ov, f'比例尺 {len(sb)} 处 · 图例 {len(leg)} 行 · 重叠={ov}')

    # ④b 比例尺整块**落在图例区让出来的那一块里**（右不越图例宽、下不进绘图区）
    # [EN] (4b) The whole scale block **fits inside the space the legend reserved** (not wider than
    # [EN] the legend column, not reaching into the drawing area)
    _ox, _oy, _cw, _ch = FP.layout_area(FP.W, FP.H, detail)
    right_edge = max((x + FP.SCALE_CELLS * FP.SCALE_CELL_W for _v, x, y in sb), default=None)
    fits = right_edge is not None and right_edge <= FP.INFO_W + 26
    ok('E4b ★★★ 比例尺**不比图例那一列更宽**（右边界不到绘图区）—— 左边那一列是'
       '唯一"别的东西都没有"的地方，宽出一格就压到地图上',
       fits, f'比例尺右={None if right_edge is None else round(right_edge)} · '
             f'绘图区左={_ox:.0f} · 图例宽={FP.INFO_W}')

    # ⑤ 绘图区**给图例让了位**（"地图部分不要跟图例重合"）
    # [EN] (5) The drawing area **gives way to the legend** ("the map must not overlap the legend")
    ox, oy, cw, ch = FP.layout_area(FP.W, FP.H, detail)
    ok('E5 ★★★ 绘图区**给图例让了位**（起点在图例实高之下、图例宽之右）'
       '—— 用户：「要注意地图部分不要跟图例重合」。'
       '不画框 ≠ 不占地方：那一带仍然不许画东西',
       ox > FP.INFO_W and oy >= LH, f'绘图区起点 ({ox:.0f},{oy:.0f}) · 图例 {FP.INFO_W}×{LH:.0f}')


# ══════════════════════════════════════════════════════════════════
#  F. 只有一个关闭按钮
# [EN] F. Only one close button
# ══════════════════════════════════════════════════════════════════
def test_close_button() -> None:
    src = (APP / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    # 取 `show_map_dialog` 的方法体
    # [EN] Take `show_map_dialog`'s method body
    body = ''
    for nd in ast.walk(tree):
        if isinstance(nd, ast.FunctionDef) and nd.name == 'show_map_dialog':
            body = ast.get_source_segment(src, nd) or ''
    ok('F1 ★★ `show_map_dialog` 的方法体取到了（判据不是空转）',
       bool(body) and 'mk_dialog' in body, f'{len(body)} 字符')

    ok('F2 ★★★ 图上**不再叠关闭按钮**（那个 `mk_icon_btn(Icons.CLOSE…)` 没了）'
       '—— 用户：「右上角 2 个关闭按钮 留外面的一个就行 **红底的关闭按钮去掉**」',
       'Icons.CLOSE' not in body, '')
    ok('F2b ★★ 而**对话框自带的那个**留着（`mk_dialog` 还在，它自带标题行的 ×）',
       'mk_dialog(' in body, '')
    ok('F2c ★ 底部那个「关闭」文字按钮也留着（它不在右上角，是常规出口）',
       "ft.TextButton(t('关闭')" in body, '')


# ══════════════════════════════════════════════════════════════════
#  G. 名字贴墙
# [EN] G. Names hug the wall
# ══════════════════════════════════════════════════════════════════
def test_labels_on_wall() -> None:
    plan, detail = _solve()
    shapes = _shapes()
    tx = _texts(shapes)

    # ① 房间名贴房间的上墙
    # [EN] (1) The room name hugs the room's top wall
    bad = []
    for name, room in plan.rooms.items():
        hit = [t for t in tx if t[0] == (name if room.here else room.label)]
        if not hit:
            bad.append(f'{name}:没写在图上')
            continue
        if abs(hit[0][2] - (room.box[1] + 15 + 1)) > 6:
            bad.append(f'{name}:y={round(hit[0][2])} 上墙={round(room.box[1])}')
    ok('G1 ★★★ 房间名**贴房间的上墙内侧**（不是飘在房间正中）'
       '—— 用户：「名字标记都放到墙的旁边 不要放到别的东西的上面」',
       bool(plan.rooms) and not bad, str(bad))

    # ② 建筑名在**房子外框之上的名字带里**（不再压在立面）
    #    ⚠⚠ 判法（2026-10-15 改）：旧判据查"名字贴着上墙 +16" —— 那其实是"压在立面"。
    #      现在楼名写在 `span[1]+4` 的带子里（房子被 `solve(name_band=…)` 推到带子下方），
    #      所以判据要查"名字的字顶**明显在房子顶墙之上**"（留 ≥6px 空隙）。
    #      回退（把楼名改回画在 `hy0+16`）时，名字字顶会落在房子顶墙之下 → 判据变红。
    # [EN] (2) The building name is **in the name band above the house frame** (no longer on the facade)
    # [EN]   ⚠⚠ Check (changed 2026-10-15): the old criterion checked "name hugs the top wall +16" --
    # [EN]   that was actually "on the facade". Now the name is written in the band at `span[1]+4`
    # [EN]   (the house is pushed below the band by `solve(name_band=…)`), so the criterion checks
    # [EN]   "the name's top is **clearly above the house top wall**" (>=6px gap). Reverting the name to
    # [EN]   `hy0+16` drops the name's top below the house top wall -> the criterion goes red.
    bname = str(tea_house().frame or '')
    hit = [t for t in tx if t[0] == bname]
    ok('G2 ★★★ 建筑名**在房子外框之上的名字带里（不压立面）**'
       '（用户 2026-10-15：「楼名字在建筑立面」）',
       bool(hit) and plan.house is not None
       and hit[0][2] < plan.house[1] - 6,
       f'{[(v, round(y)) for v, x, y, s in hit]} · 上墙 {PA._r(plan.house)}')

    # ③ 院子名贴院墙上沿
    # [EN] (3) The courtyard name hugs the courtyard wall's top edge
    hit2 = [t for t in tx if '院子' in t[0]]
    ok('G3 ★★ 院子名**贴院墙上沿内侧**',
       bool(hit2) and plan.yard is not None
       and abs(hit2[0][2] - (plan.yard[1] + 12 + 1)) <= 6,
       f'{[(v, round(y)) for v, x, y, s in hit2]} · 院墙 {PA._r(plan.yard)}')

    # ④ 小地图上也一样（两图共用 `_on_wall`）
    # [EN] (4) Same on the minimap (both share `_on_wall`)
    mms = MM.build_shapes(tea_house(), current='堂屋')
    mtx = _texts(mms)
    mhit = [t for t in mtx if t[0] == '临河茶肆']
    ok('G4 ★★ **小地图**的建筑名也贴在框的上沿（不是飘在框外面）',
       bool(mhit) and mhit[0][2] < 24,
       f'{[(v, round(x), round(y)) for v, x, y, s in mhit]}')
    ok('G5 ★★ 小地图与大地图**共用同一个贴墙函数**（`minimap._on_wall`）',
       hasattr(MM, '_on_wall')
       and 'MM._on_wall(' in (APP / 'image_gen' / 'floorplan.py').read_text(
           encoding='utf-8'), '')


# ══════════════════════════════════════════════════════════════════
#  H. 美术挂了 Reflection（AST）
# [EN] H. The art dept is wired to Reflection (AST)
# ══════════════════════════════════════════════════════════════════
def _reflect_swallows() -> bool:
    """**行为级**：让 `reflect_layout` 抛一个异常，`day_layout` 仍必须返回地图。

    ★ 为什么要行为级（2026-10-12 反例法当场抓到）：第一版只查源码里
      `'except' in body and 'return lay' in body` —— 把兜底换成 `raise`（源码里
      `except` 还在、`return lay` 也还在）判据**照样绿**（实测"没抓到"）。
      查源码证明不了"真的兜住了"，只有让它抛一下才知道。

    ⚠ 必须**还原** `reflect_layout`（`finally`）：这是 monkeypatch，
      不还原会污染同一进程里后面的判据。
    [EN] **Behavioural**: make `reflect_layout` throw and `day_layout` must still return a map.
    [EN] ★ Why behavioural (caught by the counterexample method on 2026-10-12): the first version only
    [EN] checked the source for `'except' in body and 'return lay' in body` -- replacing the fallback
    [EN] with `raise` (both strings still present) left the criterion **green** (measured as "not
    [EN] caught"). Checking source cannot prove "it really swallows"; only throwing does.
    [EN] ⚠ `reflect_layout` **must be restored** (`finally`): this is a monkeypatch, and failing to
    [EN] restore it pollutes later criteria in the same process.
    """
    from image_gen import map_layout as ML
    from image_gen import plan_audit as PAmod
    real = PAmod.reflect_layout
    try:
        def _boom(*a, **k):
            raise RuntimeError('判据探针：审核故意抛异常')
        PAmod.reflect_layout = _boom
        lay = ML.day_layout({'地点': [{'名称': '堂屋', 'x': 0.5, 'y': 0.5, '形': '屋'}],
                             '题记': '今日'},
                            ['堂屋', '井'], here='堂屋')
        return lay is not None and bool(lay.places)
    except Exception:                                            # noqa: BLE001
        return False
    finally:
        PAmod.reflect_layout = real


def test_reflection_wired() -> None:
    src = (APP / 'image_gen' / 'map_layout.py').read_text(encoding='utf-8')
    body = ''
    for nd in ast.walk(ast.parse(src)):
        if isinstance(nd, ast.FunctionDef) and nd.name == 'day_layout':
            body = ast.get_source_segment(src, nd) or ''
    ok('H1 ★★★ `day_layout` 的**方法体里真的调了** `reflect_layout`'
       '（AST 判 —— 写了没人调等于没做）'
       '—— 用户：「美术Agent绘制地图的时候要用Reflection的机制 '
       '绘制之后去审核 如果有问题则修复问题重新绘制 直到没问题」',
       'reflect_layout(' in body, f'{len(body)} 字符')

    ok('H2 ★★★ 而且**审核/修复失败不许把地图弄没**'
       '—— 增强项不许弄坏主线（**行为级**：让审核真的抛一个异常，'
       '地图仍然照原样返回）',
       _reflect_swallows(), '')
    ok('H2b ★★ 源码里也留着兜底（`except` + `return lay`）—— 行为对了，'
       '意图也该写在代码上（下一个人改这里时看得到理由）',
       'except' in body and 'return lay' in body, '')

    # ★★ 修复必须是**确定性**的（不调模型）—— Reflection 每一轮要零成本
    # [EN] ★★ The repair must be **deterministic** (no model call) -- each Reflection round must be
    # [EN] free
    pa = (APP / 'image_gen' / 'plan_audit.py').read_text(encoding='utf-8')
    ok('H3 ★★★ 修复**不调模型**（`plan_audit` 里没有 `ask(` / `llm`）'
       '—— 能算出来的事不该让模型猜（又慢又贵还不一定对）',
       'ask(' not in pa and 'llm' not in pa.replace('llm_', ''), '')


# ══════════════════════════════════════════════════════════════════
#  J. 2026-10-15 的六件几何毛病（用户按两张截图点的）
# [EN] J. The six geometry bugs of 2026-10-15 (the user pointed at them on two screenshots)
# ══════════════════════════════════════════════════════════════════
def _room_overlap(boxes: dict, tol: float = 6.0) -> list:
    """返回**真重叠**的房间对：两轴都叠过 `tol` 才算（共用一堵墙的贴合不算）。
    [EN] Return **genuinely overlapping** room pairs: both axes must overlap by >`tol`
    [EN] (a shared wall that merely touches does not count)."""
    names = list(boxes)
    bad = []
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            A, B = boxes[names[a]], boxes[names[b]]
            ox = min(A[2], B[2]) - max(A[0], B[0])
            oy = min(A[3], B[3]) - max(A[1], B[1])
            if ox > tol and oy > tol:
                bad.append((names[a], names[b], round(ox), round(oy)))
    return bad


def test_map_bugs_20261015() -> None:
    # 与用户截图同构的布局（临街楼：堂屋/后厨两间同 y、院里几样、侧案/柜格在楼外东侧）
    # [EN] A layout shaped like the user's screenshot (Mo Wen Lou: two rooms at the same y,
    # [EN] a courtyard, 侧案/柜格 east of the building)
    lay_mm = Layout(places=[
        Place('临街楼·堂屋', 0.42, 0.78), Place('后厨', 0.30, 0.78),
        Place('后院', 0.55, 0.30), Place('天井', 0.55, 0.62),
        Place('院子', 0.70, 0.55), Place('井', 0.20, 0.28),
        Place('侧案', 0.88, 0.52), Place('柜格', 0.92, 0.72),
        Place('门口台阶', 0.45, 0.95)],
        kind='室内', frame='临街楼', caption='苍痕')

    # ── N1 房间互不叠（小地图「块重叠」的真正修法）──
    # [EN] -- N1 rooms never overlap (the real fix for the minimap's "blocks overlapping") --
    d = MM.detail_of(lay_mm)
    plan_big = PA.solve(lay_mm, px=FP.layout_px(FP.W, FP.H, d),
                        span=FP.layout_span(FP.W, FP.H, d), detail=d,
                        current='临街楼·堂屋', grow=FP.PLAN_GROW,
                        name_band=FP.NAME_BAND)
    mm_boxes = MM.room_walls(lay_mm.places, W=196, H=132, pad_x=16, pad_y=15,
                             frame=(6.0, 6.0, 190.0, 117.0))
    big_bad = _room_overlap({n: r.box for n, r in plan_big.rooms.items()})
    mm_bad = _room_overlap(mm_boxes)
    ok('N1 ★★★ 房间**互不重叠**（大地图与小地图同一份几何都查）'
       '—— 用户 2026-10-15：小地图「块重叠」。两间同 y 时，旧算法把它们算成同一框；'
       '现在 `solve` 在 `shrink_off` 之后跑了分离兜底',
       not big_bad and not mm_bad,
       f'大地图 {big_bad or "无"} · 小地图 {mm_bad or "无"}')

    # ── N3 比例尺整体在绘图区**之上**（不被地图压） ──
    # ★★★ 2026-10-24 改口径：以前量的是"在绘图区之下、留 ≥8px"（那时比例尺在左下角）。
    #   用户这次的要求把它搬到了图例下面 ⇒ 守点变成"**整块都在绘图区顶之上**"。
    #   要守的意图没变：**别的东西不许压在比例尺上**。只是"别的东面"从下沿换成了
    #   整块绘图区。⚠ 阈值用 `oy`（绘图区顶）本身，不再 +8：两者之间还隔着
    #   `legend_height()` 里的 `INFO_PAD`（12px），贴不贴得上由 E4b 一起兜。
    # [EN] -- N3 the scale bar sits **above the whole drawing area** (nothing presses on it) --
    # [EN] ★★★ Re-specified 2026-10-24: it used to measure "below the drawing area, ≥8px clear" (when
    # [EN] the scale lived in the bottom-left). The user has now moved it below the legend, so the
    # [EN] criterion becomes "**the whole block is above the drawing area's top**". The intent is
    # [EN] unchanged: **nothing may press on the scale bar**; only "the other thing" changed from the
    # [EN] bottom edge to the whole drawing area.
    shapes = _shapes()
    _ox3, _oy3, _cw3, _ch3 = FP.layout_area(FP.W, FP.H, d)
    sb = [y for v, x, y, s in _texts(shapes) if '比例尺' in v]
    cells = [b[1] for b in _rects(shapes)
             if b[0] <= 130 and abs((b[2] - b[0]) - FP.SCALE_CELL_W) < 3
             and abs((b[3] - b[1]) - 9.0) < 3]
    #  ⚠ 整块的高度要算上**刻度字**：标题 13 + 尺 9 + 1 行距 + 9 号字。
    #    写成 `y + 12` 会漏掉底下那 7px —— 实测"让位漏算比例尺"那一刀下
    #    块底=214、绘图区顶=215，**差 1px 就假绿**（阈值贴边的老毛病）。
    # [EN] ⚠ The block's height must include the **graduations**: 13 title + 9 ruler + 1 + 9px type.
    # [EN] Using `y + 12` drops those 7px -- under the "reservation forgets the scale block" cut the
    # [EN] measured bottom was 214 vs a drawing-area top of 215, **1px short of red**.
    bottom = max([y + 9 + 1 + 9 for y in sb] + cells) if (sb or cells) else None
    ok('N3 ★★★ 比例尺整块在**绘图区之上**（标题到刻度字都在绘图区顶上面，'
       '地图内容压不到它）—— 用户 2026-10-24：「大地图比例尺又被挡住了」',
       bottom is not None and bottom <= _oy3,
       f'比例尺底={None if bottom is None else round(bottom)} · 绘图区顶={round(_oy3)}')

    # ── N4 「侧案」「柜格」被认成室内陈设、且落进房间 ──
    # [EN] -- N4 "侧案"/"柜格" recognised as indoor fixtures and land inside a room --
    spa = MM._spatial()
    ok('N4a ★★★ 「侧案」「柜格」被认成**室内陈设**'
       '（space_of=室内 且 _is_fixture=True）—— 用户 2026-10-15：这两样跑到墙外',
       spa.space_of('侧案') == '室内' and spa.space_of('柜格') == '室内'
       and MM._is_fixture('侧案') and MM._is_fixture('柜格'),
       f"侧案={spa.space_of('侧案')} 柜格={spa.space_of('柜格')}")
    plan4 = PA.solve(lay_mm, px=FP.layout_px(FP.W, FP.H, d),
                     span=FP.layout_span(FP.W, FP.H, d), detail=d,
                     current='临街楼·堂屋', grow=FP.PLAN_GROW,
                     name_band=FP.NAME_BAND)
    bad4 = []
    for nm in ('侧案', '柜格'):
        ent = plan4.fixtures.get(nm)
        if ent is None or ent[0] not in plan4.rooms:
            bad4.append(f'{nm}:没进房间(={ent})')
            continue
        rb = plan4.rooms[ent[0]].box
        if not PA.contains((ent[1][0] - 6, ent[1][1] - 6,
                            ent[1][0] + 6, ent[1][1] + 6), rb, tol=1.0):
            bad4.append(f'{nm}:{tuple(round(v) for v in ent[1])} 不在 {PA._r(rb)}')
    ok('N4b ★★★ 「侧案」「柜格」**落进所属房间**（用户：「家具在墙外」）',
       not bad4, str(bad4))

    # ── J1 家具**中心落在它归属的那间房**里（2026-10-17 改判大地图）──
    # ★★★ 为什么从"小地图"改成"大地图"：用户 2026-10-16 定了
    #   「小地图可以比大地图画的内容简略一个级别」「小地图就把房子或者房子以上的
    #   东西画好就可以」⇒ `minimap_lod()` 对室内/室内外一律返回 `'building'`，
    #   **小地图从此不画屋里陈设**。而这两条判据写的还是"小地图上家具方块…"
    #   ⇒ 一块也筛不出来 ⇒ 恒定红（实测 `0 块`）。这不是产品坏了，是判据在
    #   为一个**已经被推翻的设计**作证。
    #   家具真正画在**大地图**上（`floorplan._furniture`），所以"不跑到墙外 /
    #   不过大"这两件事必须在大地图上量。
    # [EN] ★★★ Why switch from "minimap" to "big map": the user settled on 2026-10-16 that
    # [EN] "the minimap can be one level simpler than the big map" / "the minimap just needs to draw
    # [EN] the house or bigger" => `minimap_lod()` returns `'building'` for indoor/indoor-outdoor, so
    # [EN] **the minimap no longer draws indoor fixtures at all**. These two criteria still said
    # [EN] "minimap fixture blocks..." => not a single block matched => permanently red (measured
    # [EN] `0 blocks`). The product is not broken; the criteria were testifying for a design that had
    # [EN] already been overturned. Fixtures are really drawn on the **big map**
    # [EN] (`floorplan._furniture`), so "not outside the wall / not oversized" must be measured there.
    bad_owner = [n for n, (owner, _pos) in plan_big.fixtures.items()
                 if owner not in plan_big.rooms]
    outside = []
    for n, (owner, pos) in plan_big.fixtures.items():
        room = plan_big.rooms.get(owner)
        if room is None:
            continue
        if not PA.contains((pos[0], pos[1], pos[0], pos[1]), room.box, tol=1.0):
            outside.append(n)
    ok('J1 ★★★ 大地图家具的**中心都在它归属的那间房**里'
       '（用户 2026-10-15：「家具在墙外」；小地图按 10-16 的决定已不画陈设，'
       '所以这条改在大地图上量）',
       bool(plan_big.fixtures) and not bad_owner and not outside,
       f'{len(plan_big.fixtures)} 件 · 归属不明 {bad_owner} · 跑到房外 {outside}')

    # ── J2 家具块尺寸有上限（绝对数，不拿产品常量自证）──
    #   ⚠ 阈值是**绝对数**（宽≤48 高≤26），不拿常量当期望 ——
    #     把 `_furniture` 里的 `w, h` 调成 60×30 这条照样红。
    #   ★ 尺寸**现量**：调产品自己的 `_furniture` 造一次块，读出来 ——
    #     不读源码字面量（那样改个变量名就假绿）。
    # [EN] ⚠ The threshold is an **absolute number** (w≤48, h≤26), not a product constant -- bumping
    # [EN] `_furniture`'s `w, h` to 60x30 still goes red.
    # [EN] ★ The size is **measured live**: call the product's own `_furniture`, read the block back --
    # [EN] do not read the source literal (renaming a variable would fake a pass).
    # ⚠ 2026-10-27 改写：原来"调 `_furniture` 造一个块、量它多大"。
    #   现在 `_furniture` **按传入的矩形画**（尺寸不再由它决定），而且"每件家具都是 40×20"
    #   恰恰是用户报的病（「家具形状和摆放位置都不对」）—— 量"一个块"已经测不到东西了。
    #   ⇒ 改成量**尺寸表的全体**，并且要求**彼此不同**：
    #     ① 一条 —— 尺寸上限（家具不该占掉半间房：房间约 200×110，最大边 ≤60）；
    #     ② 一条 —— **不能全是同一个尺寸**（那正是"家具全一样大"）。
    #   ★ 读表不算"拿产品常量自证"：尺寸的**唯一来源**就是这张表（渲染只照矩形画），
    #     所以"表里有没有失控/有没有全都一样"就是这件事的**产品定义**本身。
    # [EN] ⚠ Rewritten 2026-10-27: it used to call `_furniture` to make one block and measure it.
    # [EN] Now `_furniture` **draws into the given rectangle** (it no longer decides the size), and
    # [EN] "every piece is 40x20" is precisely the reported bug -- measuring "one block" measures
    # [EN] nothing any more. => Measure the **whole size table**, requiring (1) an upper bound (a room
    # [EN] is ~200x110, so the longest edge <= 60) and (2) **not all identical** (that is "all
    # [EN] furniture is the same size"). ★ Reading the table is not self-certification: it is the
    # [EN] **single source** of sizes (the renderer only follows the rectangle), so "is the table out
    # [EN] of hand / all the same" *is* the product definition here.
    from image_gen import furniture as _FR2
    _dims = [(round(float(sp.w), 1), round(float(sp.h), 1))
             for sp in tuple(_FR2.SPECS) + (_FR2.DEFAULT_SPEC,)]
    _uniq = {(w, h) for w, h in _dims}
    _maxe = max(max(w, h) for w, h in _dims)
    ok('J2 ★★ 家具尺寸**按类型各不相同、且都在上限内**（最大边 ≤60px；'
       '房间约 200×110 —— 家具不该占掉半间房，也不该件件一样大）',
       len(_uniq) >= 6 and _maxe <= 60.0,
       f'{len(_uniq)} 种尺寸 · 最大边 {_maxe} · 样本 {sorted(_uniq)[:5]}')

    # ── J3 成对：小地图**确实不画家具**（这是上面两条换口径的前提）──
    #   不判这一条，就没法证明"改到大地图"是必须的、而不是我在躲一条红。
    # [EN] Paired check: the **minimap really draws no fixtures** (the premise for switching the two
    # [EN] above). Without it there is no proof that "moving to the big map" was necessary rather than
    # [EN] dodging a red.
    # 小地图实际产出一份，只用来把"画了几块东西"报给人看（**不当断言口径**）
    _mms = MM.build_shapes(lay_mm, current='临街楼·堂屋', width=196, height=132,
                           title='苍痕')
    _mrect = _rects(_mms)
    ok('J3 ★★★ 成对：小地图的档位是 `building` —— 按它的契约'
       '**不画屋里陈设**（这就是 J1/J2 必须改判大地图的理由；'
       '改判不是躲红，是这两条判据在为一个已被推翻的设计作证）',
       MM.minimap_lod(lay_mm) == 'building',
       f'lod={MM.minimap_lod(lay_mm)} · 小地图共 {len(_mrect)} 个矩形')



# ══════════════════════════════════════════════════════════════════
#  I. 口径唯一（产品与判据共用同一份几何）
# [EN] I. One definition (product and criteria share the same geometry)
# ══════════════════════════════════════════════════════════════════
def test_single_definition() -> None:
    fp = (APP / 'image_gen' / 'floorplan.py').read_text(encoding='utf-8')
    ok('I1 ★★★ 绘图区 / 换算 / span 都**从 `floorplan` 里取**'
       '（`layout_area` / `layout_px` / `layout_span` 三个函数都在）'
       '—— 2026-10-12 实测过口径漂的后果：解算按画布宽、绘制按绘图区宽，'
       '家具因此跑到墙外',
       all(f'def {n}(' in fp for n in ('layout_area', 'layout_px', 'layout_span')), '')

    ok('I2 ★★★ `solve()` **收 `px` 参数**（不在内部自己算换算）'
       '—— 换算全项目只能有一份',
       'def solve(layout: Layout | None, *, px,' in
       (APP / 'image_gen' / 'plan_audit.py').read_text(encoding='utf-8'), '')


# ══════════════════════════════════════════════════════════════════
def main() -> int:
    print('═' * 62)
    print('  验证：地图几何 + 美术的 Reflection 环')
    print('═' * 62)
    try:
        print('\n【A】审核器查得出来')
        test_audit_finds()
        print('\n【B】修复真的修好（Reflection 的核心）')
        test_repair()
        print('\n【C】渲染层几何')
        test_render_geometry()
        print('\n【D】只加不减')
        test_additive()
        print('\n【E】图例与比例尺')
        test_legend()
        print('\n【F】只有一个关闭按钮')
        test_close_button()
        print('\n【G】名字贴墙')
        test_labels_on_wall()
        print('\n【H】美术挂了 Reflection')
        test_reflection_wired()
        print('\n【I】口径唯一')
        test_single_definition()
        print('\n【J】2026-10-15 六件几何毛病')
        test_map_bugs_20261015()
    except Exception:                                            # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(traceback.format_exc(), flush=True)

    bad = [c for c in report['checks'] if not c['ok']]
    report['passed'] = len(report['checks']) - len(bad)
    report['total'] = len(report['checks'])
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'plan_geometry_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  地图几何 + Reflection 验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62, flush=True)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
