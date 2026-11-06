# -*- coding: utf-8 -*-
"""验证：地图的**细致程度分档** + **室内画墙** + **大地图对话框** + **本地复用**。

用户 2026-10-12 原话（这一整段就是规格）
--------------------------------------
    「现在的小地图中间都有一个红点 这个去掉 看不见其他元素了
      另外 如果是室内地图 则请把墙画出来
      如果是室内和室外结合的地图 且需要画到室内布置的程度 比如一个茶馆
      把室内布置和院子内容刚好画到一张图里 则把室内墙和室外墙都画出来
      如果是很大的地图 比如街道图 那其实是不需要画室内的 只需要把建筑标记出来就行
      你根据地图的细致程度来判断
      还一个 我希望画 2 个地图 1 个是显示在运行界面的小地图 在左边 不需要那么精细
      还一个是这个小地图可以点 我点了之后打开一个大地图对话框（比较大的大小，
      跟对话列表的部分一样大）到那时是一个独立的对话框 点了之后可以看到详细的地图
      （这个地图按照标准室内装修或者室外普通地图的绘制方法绘制 但是可以进行一些简化）
      地图左上角带基本信息 包括地点 时间 图例 比例尺（按照地图的方法在一个方框里）
      然后右上角有关闭按钮 所有的地图保存在本地如果后续场景能够复用的话则直接复用」

判据分五组
----------
  A **细致程度**：`detail_of()` 四种档位判得对（纯函数，只看数据）
  B **红点没了**（这一轮最要紧的一条）：室内图上整座楼**不再是一个点**，
     而是"框 + 房间墙"；房间墙**真的画了出来**（矩形、够大、且不与"浅底"混淆）
  C **`kind`/`frame` 往返不丢**：写进 YAML 再读回来还是"室内 + 建筑名"
     —— 上一轮就是**丢在这一步**，用户才会看到"红点还在"
  D **大地图**：四种细致程度各自的画法、左上信息框（地点/时间/图例/比例尺）、
     右上关闭按钮、尺寸与"对话列表"同一档
  E **本地存档与复用**：存得下、读得回、指纹对不上时**不复用**

跑法：
    .venv\\Scripts\\python.exe tools/verify_map_detail.py
产出：assets/screenshots/map_detail_report.json

English:
Verification: the map's **level-of-detail tiering** + **drawing walls indoors** + **the big-map
dialog** + **local reuse**.
The user's exact words on 2026-10-12 (this whole passage is the spec)
--------------------------------------
    "every minimap now has a red dot in the middle; remove it, it hides the other elements.
      Also, if it is an indoor map, then please draw the walls;
      if it is a map combining indoors and outdoors and needs to go as far as interior layout, e.g. a
      teahouse, putting the interior layout and the courtyard contents into exactly one image, then
      draw both the indoor walls and the outdoor walls;
      if it is a very large map, e.g. a street map, then indoor drawing is not needed at all, you
      only need to mark out the buildings; you judge by the map's level of detail.
      And another thing, I want two maps drawn: 1 is the minimap shown in the run UI, on the left, it
      doesn't need to be that fine; and the other is that this minimap can be clicked -- when I click
      it, a big map dialog opens (a fairly large size, the same size as the conversation-list part),
      at that point it is an independent dialog, and after clicking you can see a detailed map (this
      map is drawn following the standard interior-decoration or ordinary outdoor map drawing method,
      though it can be simplified); the map carries basic information in its top-left, including
      location, time, legend, scale bar (in a box, the way maps do it), and then a close button in
      the top-right; all maps are saved locally, and if a later scene can reuse one, just reuse it."
Criteria are in five groups
----------
  A **level of detail**: `detail_of()` gets all four tiers right (a pure function, data only)
  B **the red dot is gone** (the most important item this round): on an indoor map the whole building
    is **no longer a point** but "a frame + room walls"; the room walls are **really drawn**
    (rectangles, big enough, not confusable with the "wash")
  C **`kind`/`frame` survive a round trip**: after writing to YAML and reading back it is still
    "indoor + building name" -- last round it was **lost right here**, which is why the user still
    saw the red dot
  D **the big map**: the drawing for each of the four tiers, the top-left info box
    (location/time/legend/scale bar), the top-right close button, and a size in the same tier as the
    "conversation list"
  E **local archive and reuse**: it saves, it reads back, and it does **not** reuse when the
    fingerprint does not match
Usage:
    .venv\\Scripts\\python.exe tools/verify_map_detail.py
Output: assets/screenshots/map_detail_report.json
"""
from __future__ import annotations

import ast
import inspect
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import flet as ft                                       # noqa: E402
import flet.canvas as fcv                               # noqa: E402
import verify_ui_common as VU                           # noqa: E402
VU.redirect_env_writes()

from image_gen import minimap as MM                     # noqa: E402
from image_gen import floorplan as FP                   # noqa: E402
from image_gen import mapstore as MS                    # noqa: E402
from image_gen.map_layout import Layout, Place          # noqa: E402
from i18n import set_lang                               # noqa: E402

set_lang('zh')
OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
#: 小地图画布的尺寸（`gui/app_flet.py` 的 `MAP_W`/`MAP_H`）—— 判据自己复算一遍
#: 房间墙的坐标要与 `build_shapes` 用**同一套**参数，对得上才说明"真的画了"。
# [EN] : the minimap canvas size (`MAP_W`/`MAP_H` in `gui/app_flet.py`) -- the criterion recomputes it
# [EN] so the room-wall coordinates use **the same** parameters as `build_shapes`; only a match proves
# [EN] "really drawn".
MM_PLACEHOLDER_W, MM_PLACEHOLDER_H = 196, 132
#: 小地图默认调色板里的"当前地点"颜色（朱砂）—— 判据拿它认"这一间被标成当前了吗"。
# [EN] : the "current place" colour in the minimap's default palette (cinnabar) -- the criterion uses it
# [EN] to tell "is this room marked as current".
C_SEAL = MM.PALETTE['here']
report: dict = {'checks': []}
_checks: list[tuple[str, bool, str]] = []


def ok(name: str, cond, detail='') -> bool:
    _checks.append((name, bool(cond), str(detail)))
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _txt(rel: str) -> str:
    return (APP / rel).read_text(encoding='utf-8')


# ══════════════════════════════════════════════════════════════════════
#  夹具：一座"茶馆"（室内 + 院子 —— 用户举的那个例子）
# [EN] Fixture: a "teahouse" (indoors + courtyard -- the example the user gave)
# ══════════════════════════════════════════════════════════════════════
def tea_house() -> Layout:
    """一座"茶馆"：**两间屋 + 一个院子**（用户举的那个例子）。

    ★ 刻意给**两间**屋（`前厅` / `堂屋`）：判据要能分辨"画了几面房间墙"，
      只有一间的话"≥2 个大矩形"会被**建筑外框**凑数（反例法当场抓出过这条）。
    [EN] A "teahouse": **two rooms + one courtyard** (the example the user gave).
    [EN] ★ Deliberately **two** rooms (`前厅` / `堂屋`): the criterion must be able to tell "how many
    [EN]   room walls were drawn", and with only one room the ">=2 big rectangles" count is padded by
    [EN]   the **building frame** (the counterexample method caught exactly this).
    """
    return Layout(
        places=[Place('门', 0.5, 0.9, shape='门'),
                Place('前厅', 0.5, 0.72, shape='屋'),
                Place('堂屋', 0.5, 0.48, shape='屋'),
                Place('柜台', 0.2, 0.6),
                Place('天井', 0.72, 0.24, shape='院'),
                Place('井', 0.86, 0.3, shape='院'),
                Place('后院', 0.5, 0.14, shape='院')],
        kind='室内', frame='临河茶肆', caption='临河茶肆')


def tea_house_with_roads() -> Layout:
    """茶馆 + **两条通路**（`links`）。

    ★★★ 为什么非要单独一个夹具（2026-10-22 实测的教训）：
      `tea_house()` **没有 `links`** —— 它的"通路"是墙上的门，不是地点之间的廊。
      于是拿它去判"道路画成什么样"时，图上一条路都没有：
      第一版 D4b2 就是这样，把产品里的双线带拆掉之后判据**照样绿**
      （凑够"成对"的是**图例里那条样板路**），而修好过滤条件之后它又**恒红**
      （图上确实没有路）。两头都错，根源是**夹具里没有要测的那个东西**。
    [EN] Teahouse **with two paths** (`links`).
    [EN] ★★★ Why a separate fixture is unavoidable (measured 2026-10-22): `tea_house()` has **no
    [EN] `links`** -- its "passages" are doors in walls, not corridors between places. So judging
    [EN] "how roads are drawn" on it sees no road at all: the first D4b2 stayed **green** after the
    [EN] product's double band was removed (the pair was satisfied by **the legend's sample road**),
    [EN] and after fixing the filter it went **permanently red** (there really is no road). Both wrong,
    [EN] and the root is the same: **the fixture did not contain the thing being measured**.
    """
    base = tea_house()
    base.links = [{'a': '门', 'b': '前厅', 'kind': '路'},
                  {'a': '前厅', 'b': '堂屋', 'kind': '路'},
                  {'a': '堂屋', 'b': '天井', 'kind': '路'}]
    return base


def indoor_only() -> Layout:
    """只有屋里（没有院子）—— `室内` 那一档。
    [EN] Indoors only (no courtyard) -- the `室内` tier."""
    return Layout(places=[Place('堂屋', 0.4, 0.5, shape='屋'),
                          Place('柜台', 0.62, 0.5)],
                  kind='室内', frame='临河茶肆')

def street() -> Layout:
    """街道图（一堆地点铺开，没有屋里空间）—— `整体` 那一档。
    [EN] A street map (a spread of places, no indoor space) -- the `整体` tier."""
    return Layout(places=[Place(n, 0.08 + 0.17 * i, 0.5, shape='屋')
                          for i, n in enumerate('甲乙丙丁戊己')],
                  links=[{'a': '甲', 'b': '乙', 'kind': '路'},
                         {'a': '乙', 'b': '丙', 'kind': '路'}],
                  kind='整体', caption='某某镇')


def _counts(shapes) -> dict:
    return MM.shape_counts(shapes)


def _rects(shapes):
    return [s for s in shapes if isinstance(s, fcv.Rect)]


def _texts(shapes) -> list[str]:
    return [str(getattr(s, 'value', '') or '') for s in shapes
            if type(s).__name__ == 'Text']


# ══════════════════════════════════════════════════════════════════════
#  A 细致程度（纯函数）
# [EN] A Level of detail (a pure function)
# ══════════════════════════════════════════════════════════════════════
def test_detail() -> None:
    rep = {}
    cases = [
        ('室内外（茶馆：屋里 + 院子）', tea_house(), MM.DETAIL_IN_OUT),
        ('室内（只有屋里）', indoor_only(), MM.DETAIL_IN),
        ('整体（街道图：一堆地点铺开）', street(), MM.DETAIL_WHOLE),
        ('局部（设定里的一处地点）',
         Layout(places=[Place('临河茶肆', 0.3, 0.4, shape='楼')], kind='局部'),
         MM.DETAIL_LOCAL),
        ('老缓存（没有 kind，但有屋里空间 + 院子）',
         Layout(places=[Place('堂屋', 0.3, 0.4, shape='屋'),
                        Place('井', 0.7, 0.6, shape='院')]),
         MM.DETAIL_IN_OUT),
        ('老缓存（没有 kind，只有一处建筑）',
         Layout(places=[Place('临河茶肆', 0.5, 0.5, shape='楼')]),
         MM.DETAIL_LOCAL),
    ]
    got = {}
    for label, lay, want in cases:
        got[label] = MM.detail_of(lay)
    rep['detail'] = got
    bad = [k for k, _l, w in cases if got[k] != w]
    ok('A1 ★★★ 四种细致程度判得对（含"老缓存没有 kind"时按名字自己判）'
       f'（{len(cases)} 个例子）', not bad,
       f'判错：{[(k, got[k]) for k, _l, _w in cases if k in bad]}' if bad else str(got))
    ok('A2 ★★ 空布局 / 没有地点时不炸（返回一个合理档位）',
       MM.detail_of(None) in (MM.DETAIL_LOCAL, MM.DETAIL_WHOLE)
       and MM.detail_of(Layout()) in (MM.DETAIL_LOCAL, MM.DETAIL_WHOLE),
       f'{MM.detail_of(None)} / {MM.detail_of(Layout())}')
    # ★ 细致程度是**纯函数**（同一份输入永远同一个答案）—— 这是"存本地复用"的前提
    # [EN] ★ Level of detail is a **pure function** (same input, same answer forever) -- the premise
    # [EN] for "save locally, reuse later"
    same = {MM.detail_of(tea_house()) for _ in range(5)}
    ok('A3 ★★ 同一份布局**每次判出同一个档位**（纯函数 —— 复用的前提）',
       len(same) == 1, str(same))


# ══════════════════════════════════════════════════════════════════════
#  B 红点没了 + 室内画墙
# [EN] B The red dot is gone + walls are drawn indoors
# ══════════════════════════════════════════════════════════════════════
def test_walls() -> None:
    rep = {}
    lay = tea_house()
    shapes = MM.build_shapes(lay, current='堂屋')
    rects = _rects(shapes)
    texts = _texts(shapes)
    rep['tea'] = {'n_rect': len(rects), 'texts': texts,
                  'sizes': [(round(r.width or 0), round(r.height or 0)) for r in rects]}

    # ① **红点的两个来源都要堵住**（这是这一轮最要紧的一条）
    #   来源甲：`day_layout` 发现"当前场景"不在图上时，**补一个大号"楼"摆在正中间**
    #           —— 渲染那边还会给当前地点垫朱砂，于是正中间一个又大又红的点。
    #   来源乙：渲染时把"当前地点"画在**图上根本没有的位置**（名字对不上）。
    # [EN] ① **Both red-dot sources must be plugged** (the most important item this round)
    # [EN]   Source A: when `day_layout` finds "the current scene" missing from the map it **appends a
    # [EN]     large "building" glyph dead centre** -- and the renderer pads the current place with
    # [EN]     cinnabar, giving a large red dot right in the middle.
    # [EN]   Source B: the renderer draws "the current place" at **a position that isn't on the map at
    # [EN]     all** (the name doesn't match).
    from image_gen.map_layout import day_layout, resolve_place
    d = day_layout({'地点': [{'名称': '堂屋', 'x': 0.4, 'y': 0.5, '形': '屋'},
                             {'名称': '井', 'x': 0.7, 'y': 0.6, '形': '院'}],
                    '题记': '今日'},
                   ['堂屋', '井'], here='临河茶肆·堂屋')
    rep['b1a'] = {'names': [p.name for p in d.places], 'frame': d.frame}
    ok('B1a ★★★ 当前场景写成**子地点**（`临河茶肆·堂屋`）时，'
       '**不再补一个假的大"楼"摆在正中间**'
       '（用户：「现在的小地图中间都有一个红点 这个去掉 看不见其他元素了」）',
       not any(p.name == '临河茶肆·堂屋' for p in d.places)
       and '堂屋' in [p.name for p in d.places], str(rep['b1a']))

    ok('B1b ★★ 而名字**对得上**：`临河茶肆·堂屋` 落到图上的 `堂屋`'
       '（对上了朱砂圈才会落在那一间，而不是落到正中间）',
       resolve_place(d, '临河茶肆·堂屋') == '堂屋'
       and resolve_place(d, '雾泽') == '', '')

    # ★★ **渲染这一侧也要真的用它**（只在 `day_layout` 里对上不够）：
    #   拿一个"当前场景是子地点"的图去画，朱砂圈必须落在**那一间**上。
    #   ⚠ 反例法当场抓到过：只测 `resolve_place()` 这个函数的话，
    #     把渲染里那次调用删掉判据照样绿 —— 而屏幕上红点回来了。
    # [EN] ★★ **The rendering side must really use it too** (matching inside `day_layout` is not
    # [EN] enough): draw a map whose "current scene" is a sub-location and the cinnabar ring must land
    # [EN] on **that room**.
    # [EN] ⚠ The counterexample method caught this: testing only the `resolve_place()` function left
    # [EN] the criterion green after deleting that call in the renderer -- while the red dot came back
    # [EN] on screen.
    sub = MM.build_shapes(tea_house(), current='临河茶肆·堂屋')
    here_marks = [s for s in sub
                  if type(s).__name__ == 'Text'
                  and getattr(s, 'value', '') == '堂屋']
    ok('B1c ★★★ 渲染时**真的把"当前地点"对到图上的房间**：'
       '`临河茶肆·堂屋` 画出来是"堂屋"那一间被标成**当前**（朱砂）',
       bool(here_marks) and all(
           str(getattr(getattr(s, 'style', None), 'color', '')) == str(C_SEAL)
           for s in here_marks),
       f'堂屋的字 {[(getattr(s, "value"), getattr(getattr(s, "style", None), "color", None)) for s in here_marks]}')

    # ★★ **真对不上时**（模型漏了这一处）才补 —— 补出来的那个**不许是"整座建筑"**
    #    摆在正中间（那正是用户报的那个红点）。
    # [EN] ★★ Only when it **truly cannot be matched** (the model missed this spot) is one appended --
    # [EN] and it must **not be a "whole building"** dead centre (that is exactly the red dot the user
    # [EN] reported).
    from image_gen.map_layout import day_layout as _day_layout
    miss = _day_layout({'地点': [{'名称': '堂屋', 'x': 0.4, 'y': 0.5, '形': '屋'}],
                        '题记': '今日'}, ['堂屋'], here='雾泽渡口')
    ph = next((p for p in miss.places if p.name == '雾泽渡口'), None)
    ok('B1d ★★★ 对不上时的**兜底记号不是"整座建筑"、也不摆在正中间**'
       '（补一个 `楼·大` 在 0.5/0.62 就是用户看到的那个红点）',
       ph is not None and ph.shape != '楼' and ph.size != '大' and ph.y > 0.6,
       f'{(ph.shape, ph.size, ph.x, ph.y) if ph else None}')

    # ── B1e ★★★ **大地图上没有实心红圆**（2026-10-14 用户第 4 次报同一类问题）──
    #   用户原话：「大地图里还有有一个红圆形 旁边标记名字
    #              大地图里也不要这个红色圆形」。
    #   ⚠ 为什么之前 36/36 全绿却漏了它：B 段前 10 条查的是
    #     "当前地点**对没对上**图上的房间"（`map_layout` 那一层的数据），
    #     **没有一条查"`floorplan` 画出来的形状里有没有那个实心圆"**（渲染层）。
    #     ⇒ 数据对了、渲染里还盖着一个红圆，判据看不见。
    #   ⇒ 这条**自己造大地图形状、直接数形状**：
    #     `fcv.Circle` 且**实心填充**（`PaintingStyle.FILL`）且颜色是朱砂的 —— 一个都不许有。
    #   ★★ **两条路都要测**（第一次写漏了，反例法当场抓到）：
    #     那个实心红圆长在 `floorplan._symbol()` 里，而 `_symbol` **只画室外地点**；
    #     室内房间走的是 `_furniture()` / 房间墙那条路（垫朱砂矩形 + 房间名）。
    #     ⇒ 只测"室内当前地点"根本走不到那段代码，变异把圆加回去**也不会红**。
    #     所以下面 indoor / outdoor 各造一份，两条分支都数。
    #   ★ 与 minimap 同一套约定（那边用户报过三次）：当前地点只靠
    #     **名字的朱砂色 + 加粗**表示（见 `minimap.build_shapes` 的 `bold=here`）。
    # [EN] ── B1e ★★★ **no filled red circle on the big map** (4th time the user reported this class of
    # [EN] problem, 2026-10-14) ──
    # [EN] ⚠ Why 36/36 green still missed it: the first ten B checks verify "does the current place
    # [EN] **line up** with a room on the map" (the `map_layout` data layer). **None asked whether the
    # [EN] shapes `floorplan` draws contain that filled circle** (the render layer). => The data can be
    # [EN] right while a red circle is still stamped on top, invisible to the criteria.
    # [EN] ⇒ This one **builds the big map's shapes itself and counts shapes directly**: no
    # [EN] `fcv.Circle` may be **filled** (`PaintingStyle.FILL`) with the cinnabar colour.
    # [EN] ★★ **Both branches must be tested** (the first draft missed this and the reverse harness
    # [EN] caught it on the spot): that filled circle lives in `floorplan._symbol()`, which **only draws
    # [EN] outdoor places**; indoor rooms take the `_furniture()` / room-wall path (cinnabar-washed rect
    # [EN] + room name). => Testing only an indoor current place never reaches that code, and putting the
    # [EN] circle back **would not go red**. So the two branches are each built and counted below.
    # [EN] ★ Same convention as the minimap (where the user reported it three times): the current place
    # [EN] is shown only by **the name's cinnabar colour + bold**.
    import gui.app_flet as _G                                     # noqa: PLC0415
    _pal = {'paper': _G.C['input_bg'], 'ink': _G.C['text'],
            'muted': _G.C['muted'], 'water': _G.C['accent'],
            'link': _G.C['border'], 'wall': _G.C['border'],
            'wall_hi': _G.C['border_ink'], 'furniture': _G.C['hover'],
            'ground': _G.C['paper_lo'], 'grid': _G.C['hover'],
            'here': _G.C['seal'], 'frame': _G.C['text'],
            'on_paper': _G.C['input_bg']}
    _here_rgb = str(_pal['here'])

    def _fp_shapes_for(cur: str) -> list:
        return FP.build_detail_shapes(tea_house(), current=cur, place='临河茶肆',
                                      when='第 3 天 · 戌时', palette=_pal)

    def _red_filled_circles(shs: list) -> list:
        out = []
        for _s in shs:
            if not isinstance(_s, fcv.Circle):
                continue
            _pt = getattr(_s, 'paint', None)
            if _pt is None:
                continue
            if (str(getattr(_pt, 'style', '')).endswith('FILL')
                    and _here_rgb.lower() in str(getattr(_pt, 'color', '') or '').lower()):
                out.append((getattr(_s, 'x', '?'), getattr(_s, 'y', '?'),
                            getattr(_s, 'radius', '?')))
        return out

    # 室内（堂屋=房间）与室外（后院=地点记号）各一份 —— 两条渲染分支
    _sh_in = _fp_shapes_for('堂屋')
    _sh_out = _fp_shapes_for('后院')
    _bad_in = _red_filled_circles(_sh_in)
    _bad_out = _red_filled_circles(_sh_out)
    rep['red_circle'] = {'indoor': _bad_in, 'outdoor': _bad_out}
    ok('B1e ★★★ 大地图上**一个"实心朱红圆"都没有**（用户："大地图里也不要这个红色圆形"）'
       '—— **室内（房间那条路）与室外（地点记号那条路）各测一份**，'
       '当前地点只靠名字的**朱砂色 + 加粗**表示（与 minimap 同一套约定）',
       not _bad_in and not _bad_out,
       f'室内实心朱砂圆 {len(_bad_in)} 个 / 室外 {len(_bad_out)} 个：'
       f'{(_bad_in + _bad_out)[:3]}')

    # B1f ★★ 成对：**"当前地点"仍然看得出来**（别为了过 B1e 把标记整个删了、
    #   变成"在图上找不到自己在哪"）—— 两份图上都得有朱砂字。
    def _red_texts(shs: list) -> list:
        return [str(getattr(s, 'value', '') or '') for s in shs
                if isinstance(s, fcv.Text)
                and _here_rgb.lower() in str(getattr(getattr(s, 'style', None),
                                                     'color', '') or '').lower()]
    _t_in = _red_texts(_sh_in)
    _t_out = _red_texts(_sh_out)
    rep['here_texts'] = {'indoor': _t_in, 'outdoor': _t_out}
    ok('B1f ★★ 成对：**室内 / 室外两份图上当前地点都仍是朱砂色**'
       '（把标记删干净能过 B1e，但那样图上就找不到"我在哪"了）',
       bool(_t_in) and bool(_t_out),
       f'室内朱砂字={_t_in} / 室外朱砂字={_t_out}')

    # ② 房间墙：**真的画了**（用 `room_walls()` 直接问"算出来几面"，
    #    不靠数画布上的矩形 —— 院墙与外框也都是矩形，数不准会假绿）
    # [EN] ② Room walls: **really drawn** (ask `room_walls()` how many it computes, rather than counting
    # [EN] rectangles on the canvas -- the courtyard wall and the frame are rectangles too, and
    # [EN] miscounting gives false green)
    outdoor = [p for p in lay.places if MM._is_outdoor(p.name)]
    boxes = MM.room_walls(lay.places, W=MM_PLACEHOLDER_W, H=MM_PLACEHOLDER_H,
                          pad_x=16, pad_y=15, frame=(6.0, 6.0,
                                                     MM_PLACEHOLDER_W - 6.0,
                                                     MM_PLACEHOLDER_H - 15.0))
    wash = [r for r in rects if r.width and 24 <= r.width <= 50
            and r.height and 16 <= r.height <= 40]
    # 图上真的出现了那些房间墙（按坐标对上，不是"数大矩形"）
    # [EN] Those room walls really appear on the map (matched by coordinates, not by "counting big
    # [EN] rectangles")
    drawn = [r for r in rects
             if r.width and r.height and any(
                 abs(float(getattr(r, 'x', 0) or 0) - b[0]) < 1.5
                 and abs(float(getattr(r, 'y', 0) or 0) - b[1]) < 1.5
                 and abs(float(r.width) - (b[2] - b[0])) < 1.5
                 and abs(float(r.height) - (b[3] - b[1])) < 1.5
                 for b in boxes.values())]
    rep['b2'] = {'n_rooms': len(boxes), 'n_drawn': len(drawn),
                 'n_wash': len(wash), 'n_outdoor': len(outdoor)}
    ok('B2 ★★★ 室内图上**真的画了房间墙**（有几间就画几块，按坐标对得上）；'
       '而"院里浅底"**只给屋外那些点垫**（一块不多一块不少）—— 两者不混',
       len(boxes) >= 2 and len(drawn) >= len(boxes)
       and len(wash) == len(outdoor), str(rep['b2']))

    # ⚠ 这里要断言的是**绝对下限**，**不能**拿 `MM.ROOM_MIN_W` 去比 ——
    #   反例法当场抓出过这个自证陷阱：把那个常量改小（房间墙退化成小方块），
    #   判据跟着改小，照样绿。而"房间墙必须比浅底大"是个**绝对**要求
    #   （浅底窗口是 24~50 宽、16~40 高，房间墙必须**明显超过**它，
    #   否则两者在图上分不出来 —— 而这条正是"屋里见顶、院里见天"的保障）。
    # [EN] ⚠ What is asserted here must be an **absolute lower bound**, **not** a comparison against
    # [EN] `MM.ROOM_MIN_W` -- the counterexample method caught this self-proving trap: shrink that
    # [EN] constant (walls degenerate into small blocks) and the criterion shrinks with it and stays
    # [EN] green. "A room wall must be bigger than a wash" is an **absolute** requirement (the wash
    # [EN] window is 24~50 wide and 16~40 high, and a room wall must **clearly exceed** it, otherwise
    # [EN] the two cannot be told apart on the map -- and that is exactly the guarantee behind "rooms
    # [EN] have a roof, the yard has open sky").
    room = [r for r in rects if r.width and r.width > 50 and r.height and r.height > 40]
    ok('B3 ★★★ 房间墙的尺寸**明显超过"院里浅底"那个窗口**'
       '（宽 > 50 且高 > 40 —— 不然两者在图上分不出来），'
       '而且不小于代码里声明的最小尺寸',
       bool(room) and MM.ROOM_MIN_W > 50 and MM.ROOM_MIN_H > 40,
       f'大矩形 {[(round(r.width or 0), round(r.height or 0)) for r in room]}'
       f' · 常量 {MM.ROOM_MIN_W}×{MM.ROOM_MIN_H}')

    ok('B4 ★★ 房间名写在**房间里**（平面图就是这么标的）',
       '堂屋' in texts, str(texts))

    # ③ 室内外：**两种墙都画**（用户点名的那句）
    # [EN] ③ Indoor+outdoor: **both kinds of wall are drawn** (the words the user named)
    yard = [r for r in rects if r.width and r.width >= MM.YARD_MIN_W
            and r.height and r.height >= MM.YARD_MIN_H]
    ok('B5 ★★★ 茶馆这种（室内 + 院子）**室内墙与室外墙都画**'
       '（用户：「则把室内墙和室外墙都画出来」）',
       bool(room) and bool(yard) and '院' in texts,
       f'房间墙 {len(room)} 块 · 院墙 {len(yard)} 块 · 文字 {texts}')

    # ④ 街道图：**不画室内**
    # [EN] ④ Street map: **no indoor drawing**
    st = MM.build_shapes(street(), current='甲')
    s_rects = _rects(st)
    s_wall_like = [r for r in s_rects if r.width and r.width > 50 and r.height
                   and r.height > 40 and float(getattr(r, 'x', 0) or 0) >= 3]
    rep['b6'] = {'n_rect': len(s_rects), 'wall_like': len(s_wall_like)}
    ok('B6 ★★★ 街道图**不画室内**（没有整座楼的大框、也没有房间墙）'
       '——「如果是很大的地图 比如街道图 那其实是不需要画室内的」',
       not s_wall_like, str(rep['b6']))
    ok('B7 ★★ 街道图**把建筑标记出来**了（每个地点都有自己的名字）',
       all(str(n) in _texts(st) for n in '甲乙丙丁戊己'), str(_texts(st))[:120])


# ══════════════════════════════════════════════════════════════════════
#  C kind/frame 往返不丢（上一轮红点没消掉的真凶）
# [EN] C kind/frame survive a round trip (the real culprit behind last round's lingering red dot)
# ══════════════════════════════════════════════════════════════════════
def test_roundtrip() -> None:
    rep = {}
    from image_gen.map_layout import normalize
    lay = tea_house()
    back = Layout.from_dict(lay.to_dict())
    rep['layout'] = {'kind': back.kind, 'frame': back.frame}
    ok('C1 ★★★ `Layout.to_dict()` → `from_dict()` **不丢 `kind`/`frame`**',
       back is not None and back.kind == '室内' and back.frame == '临河茶肆',
       str(rep['layout']))

    # ⚠ 真正的坑在这里：`Atlas.from_dict` 读局部/室内层走的是 **`normalize()`**，
    #   而上一轮 `normalize()` 压根没读这两个键 ⇒ 室内标签**每次回读都丢**。
    # [EN] ⚠ The real trap is here: `Atlas.from_dict` reads the local/indoor layers through
    # [EN] **`normalize()`**, and last round `normalize()` never read those two keys ⇒ the indoor tag
    # [EN] was **lost on every read-back**.
    n = normalize(lay.to_dict(), [], source='atlas')
    rep['normalize'] = {'kind': n.kind, 'frame': n.frame}
    ok('C2 ★★★ `normalize()`（**底图读回走的就是它**）也保留 `kind`/`frame`'
       '—— 上一轮红点没消掉就是因为这里丢标签',
       n.kind == '室内' and n.frame == '临河茶肆', str(rep['normalize']))

    # 老缓存（文件里根本没有这两个键）→ 按**桶名**兜底补回来
    # [EN] An old cache (with neither key in the file) -> backfilled from the **bucket name**
    from world import atlas as AT
    old = {'名称': '小世界地图',
           '室内': {'临河茶肆': {'source': 'atlas', 'caption': '',
                                'places': [{'name': '堂屋', 'x': 0.4, 'y': 0.5,
                                            'shape': '屋'}]}},
           '局部': {'临河茶肆': {'source': 'atlas', 'caption': '',
                                'places': [{'name': '门前街', 'x': 0.5, 'y': 0.5,
                                            'shape': '屋'}]}}}
    at = AT.Atlas.from_dict(old)
    rep['old_cache'] = {
        'indoor': {k: (v.kind, v.frame) for k, v in (at.indoor or {}).items()},
        'local': {k: (v.kind, v.frame) for k, v in (at.local or {}).items()}}
    ok('C3 ★★★ **老缓存**（文件里没有 `kind`/`frame`）读回来**自动补成"室内 + 建筑名"**'
       '—— 用户手上那份底图就是这样，不补的话他打开还是看到红点',
       at.indoor.get('临河茶肆') is not None
       and at.indoor['临河茶肆'].kind == '室内'
       and at.indoor['临河茶肆'].frame == '临河茶肆',
       str(rep['old_cache']))
    ok('C4 ★ 而**局部**层补的是 `局部`、**不给它安建筑名**'
       '（局部图不该框整座建筑）',
       at.local.get('临河茶肆') is not None
       and at.local['临河茶肆'].kind == '局部'
       and at.local['临河茶肆'].frame == '',
       str(rep['old_cache']['local']))


# ══════════════════════════════════════════════════════════════════════
#  D 大地图（对话框的内容与画法）
# [EN] D The big map (the dialog's content and drawing)
# ══════════════════════════════════════════════════════════════════════
def test_big_map() -> None:
    rep = {}
    # ① 尺寸与"对话列表"同一档
    # [EN] ① Same size tier as the "conversation list"
    src = _txt('gui/app_flet.py')
    rep['geo'] = {'w': None, 'h': None, 'canvas': None}
    for line in src.splitlines():
        if line.startswith('MAP_DLG_W = '):
            rep['geo']['w'] = line.split('=')[1].strip()
        if line.startswith('MAP_DLG_H = '):
            rep['geo']['h'] = line.split('=')[1].strip()
        if line.startswith('MAP_DLG_CANVAS_W = '):
            rep['geo']['canvas'] = line.split('=')[1].strip()
    log_w = next((l.split('=')[1].strip() for l in src.splitlines()
                  if l.startswith('LOG_DLG_W = ')), '')
    log_h = next((l.split('=')[1].strip() for l in src.splitlines()
                  if l.startswith('LOG_DLG_H = ')), '')
    ok('D1 ★★ 大地图对话框**与日志/对话栏同一档大小**'
       f'（用户：「比较大的大小，跟对话列表的部分一样大」）',
       rep['geo']['w'] == log_w and rep['geo']['h'] == log_h,
       f'地图 {rep["geo"]["w"]}×{rep["geo"]["h"]} vs 日志 {log_w}×{log_h}')

    # ★★★ 2026-10-27（用户）：「大地图里生成的地图在右下角 都出了对话框边界」。
    #   根因之一是**声明了尺寸却没用**：文档写 1000×700，代码里实际用
    #   `MAP_DLG_CANVAS_W × (MAP_DLG_CANVAS_H + 40)` = 940×640（窄 60、矮 60），
    #   于是画布 + 一换行的提示就顶到边框外。
    #   ⇒ 这一条**不查常量声明**（D1 已经在查），而是查**调用点用的是哪个尺寸** ——
    #     "常量写了不用"是本项目栽过多次的坑，只测声明等于没测。
    # [EN] ★★★ 2026-10-27 (the user): "the map sits in the bottom-right and runs outside the
    # [EN] dialog". One root cause was **declaring a size and not using it**: the docstring promises
    # [EN] 1000x700 while the code used `MAP_DLG_CANVAS_W x (MAP_DLG_CANVAS_H + 40)` = 940x640 (60
    # [EN] narrower, 60 shorter), so the canvas plus one wrapped hint line overflowed the frame.
    # [EN] => This check does **not** read the constants (D1 already does); it reads **which size the
    # [EN] call site actually passes**. "A constant written but not used" is a repeated pit here;
    # [EN] testing only the declaration tests nothing.
    dlg_src = '\n'.join(src.splitlines()[src.splitlines().index(
        next(l for l in src.splitlines() if 'MAP_DLG_CANVAS_W = ' in l)):])
    use_ok = 'width=MAP_DLG_W' in dlg_src and 'height=MAP_DLG_H' in dlg_src
    ok('D1b ★★★ 大地图对话框**真的用了**声明的 1000×700（不是 940×640）'
       '（用户："出了对话框边界"：容器比声明的窄 60、矮 60，画布加提示就溢出）',
       use_ok,
       '容器尺寸用了 MAP_DLG_W/H' if use_ok else '容器没用 MAP_DLG_W/H（声明形同虚设）')

    # ② 左上信息框：地点 / 时间 / 图例 / 比例尺
    # [EN] ② Top-left info box: location / time / legend / scale bar
    shapes = FP.build_detail_shapes(tea_house(), current='堂屋', place='临河茶肆',
                                    when='第 3 天 · 戌时')
    texts = _texts(shapes)
    need = ['临河茶肆', '时间：第 3 天 · 戌时', '图例', '比例尺（示意）']
    rep['info'] = [x for x in texts if x.startswith(('时间：', '图例', '比例尺'))]
    ok('D2 ★★★ 左上角信息框四样齐全（**地点 · 时间 · 图例 · 比例尺**）'
       '—— 用户：「地图左上角带基本信息 包括地点 时间 图例 比例尺」',
       all(n in texts for n in need), f'缺={[n for n in need if n not in texts]}')

    # 信息框是**一个方框**（左上角那一带有一个矩形，且不是纸底）
    # [EN] The info box is **a box** (a rectangle in the top-left area, and it is not the paper
    # [EN] base)
    box = [r for r in _rects(shapes)
           if r.width and r.height and abs(float(r.width) - FP.INFO_W) < 3
           and abs(float(r.height) - FP.INFO_H) < 3
           and float(getattr(r, 'x', 0) or 0) < 40 and float(getattr(r, 'y', 0) or 0) < 40]
    # ⚠ 2026-10-12 改口径（用户第二轮）：「左上角的图例 **不要带方框了**
    #   但是要注意**地图部分不要跟图例重合**」。
    #   ⇒ 方框**不画了**，"不重合"改由**占位**保证（绘图区从图例右边/下边开始）。
    #   判据跟着改：查"方框没了" **且** "绘图区真的让了位"。
    # [EN] ⚠ Convention changed on 2026-10-12 (the user's second round): "the top-left legend
    # [EN] **should not have a box**, but note that **the map must not overlap the legend**".
    # [EN] ⇒ the box is **no longer drawn**, and "no overlap" is now guaranteed by **reserving space**
    # [EN] (the drawing area starts to the legend's right/below). The criterion follows: check "the box
    # [EN] is gone" **and** "the drawing area really gave way".
    _det = MM.detail_of(tea_house())
    _ox, _oy, _cw, _ch = FP.layout_area(FP.W, FP.H, _det)
    ok('D3 ★★★ 这四样**不再圈方框了**（用户第二轮：「不要带方框了」）'
       '—— 但仍然**占位**：绘图区从图例的右边/下边开始（"不重合"是算出来的）',
       not box and _ox > FP.INFO_W and _oy >= FP.legend_height(_det) - 1,
       f'方框 {len(box)} 个 · 绘图区起点 ({_ox:.0f},{_oy:.0f}) · '
       f'图例 {FP.INFO_W}×{FP.legend_height(_det):.0f}')

    ok('D4 ★★ 图例的记号是**照实画出来的**（不是写一句"虚线表示路"）',
       len([s for s in shapes if isinstance(s, fcv.Path)
            or type(s).__name__ in ('Arc', 'Circle')]) > 5
       and '房间墙' in texts and '门（缺口 + 门扇）' in texts,
       str([x for x in texts if '墙' in x or '门' in x]))

    # ══════════════════════════════════════════════════════════════
    #  D4b ★★★ 道路：**实心带**、图例里有它、而且**没有虚线了**
    #
    #  用户两轮把这件事说清楚了：
    #    · 2026-10-22 第一轮「**大地图里的两条虚线有什么用处？**」
    #      —— 那两条是 `layout.links` 画的通路，细虚线（2.0 宽 + dash）跟网格线一个量级，
    #      在测绘纸上根本读不出来，所以他才问"有什么用"；
    #    · 第二轮「**去掉虚线 但是换一个更明显的画法绘制道路**」
    #      —— 他要的是**路**，不是删掉，也不是细线。
    #  ⇒ 现在：双线实心带（外 `ROAD_OUTER` = 7、内 `ROAD_INNER` = 4.2，圆头），
    #    与街道图同一套画法但细一档。
    #
    #  三条一起判（缺一条都出现过问题）：
    #    ① **图上没有虚线**（`stroke_dash_pattern` 一条都不许有）；
    #    ② 图上**有**够宽的道路带（≥ `ROAD_INNER`，且成对：每条路两个宽度）；
    #    ③ 图例里有「道路」，而且**记号画法与图上一致**（同样的两个宽度）。
    #  ⚠ 判"有道路"必须看**宽度**，不能只看"有线"：旧版也是线，而且很多条。
    # [EN] D4b: roads are **solid bands**, the legend lists them, and there are **no dashed lines**.
    # [EN] The user said it in two rounds: "what are the two dashed lines for?" (they were
    # [EN] `layout.links` drawn as a 2.0-wide dashed line, the same weight as the survey grid, hence
    # [EN] unreadable) and then "remove the dashed lines but draw the roads in a more obvious way".
    # [EN] => Now: a solid double-line band (outer `ROAD_OUTER` = 7, inner `ROAD_INNER` = 4.2, round
    # [EN] caps), the street-map convention one tier thinner.
    # [EN] Three things judged together (each has failed before): ① **no dashed line on the map**
    # [EN] at all; ② the map **has** bands at least `ROAD_INNER` wide, in pairs (edge + surface);
    # [EN] ③ the legend lists "道路" and its **mark uses the same two widths** as the map.
    # [EN] ⚠ "Has roads" must be judged by **width**, not by "there are lines" -- the old version had
    # [EN] plenty of lines too.
    # ══════════════════════════════════════════════════════════════
    # ★ 这一组（道路 + 门）用**带通路**的夹具：`tea_house()` 没有 `links`，
    #   图上一条路都没有（见 `tea_house_with_roads` 的说明）。
    # [EN] This group (roads + doors) uses the **fixture with paths**: `tea_house()` has no `links`
    # [EN] so its map has no road at all (see `tea_house_with_roads`).
    _lay8 = tea_house_with_roads()
    _det8 = MM.detail_of(_lay8)
    shapes = FP.build_detail_shapes(_lay8, current='堂屋', place='临河茶肆',
                                    when='第 3 天 · 戌时')
    _dashed = [s for s in shapes
               if isinstance(s, fcv.Line)
               and getattr(getattr(s, 'paint', None), 'stroke_dash_pattern', None)]
    ok('D4b ★★★ 图上**一条虚线都没有**（用户 2026-10-22：「去掉虚线」）'
       '—— 旧版那两条 `dash=[9,6]` 的通路是"看不懂"的根源',
       not _dashed, f'虚线 {len(_dashed)} 条')

    def _widths(seq) -> list:
        out = []
        for x in seq:
            try:
                out.append(round(float(getattr(getattr(x, 'paint', None),
                                               'stroke_width', 0) or 0), 2))
            except (TypeError, ValueError):
                continue
        return out

    # ══════════════════════════════════════════════════════════════
    # ★★★ 2026-10-26 判据**反转**（产品被用户明确改过，判据必须跟着转）
    #
    # 用户原话：「地图中 如果是室内图 **把路去掉** 如果是室外地图 按照标准地图画法绘制道路等所有元素」
    #
    # 原来这里有两条判据（D4b2 / D4b3）要求"室内图必须画出成对的路带、图例里也必须有一条路"。
    # 它们在当时是对的（2026-10-22 用户说"换一个更明显的画法绘制道路"），
    # 但在 2026-10-26 之后**方向反了** —— 继续留着就不是"保护"而是"逼产品犯错"。
    # ⇒ 反转成：室内图**一条路带都不许有**，图例里也**不许有"道路"这一条**。
    #
    # ⚠ 判法仍按**形态**（外圈 wall 色 ≥5 + 内芯 paper 色 ≥3 的同坐标双线对），
    #   不看 `ROAD_OUTER` 这种实现参数 —— 那两个常量已经删了，而"换个宽度加回来"
    #   这种事恰恰是判据该拦住的。
    # [EN] ★★★ 2026-10-26 the criteria are **inverted** (the product was changed on the user's
    # [EN] explicit request; criteria must follow): "if it is an indoor plan, **remove the roads**".
    # [EN] D4b2 / D4b3 used to demand paired road bands plus a road entry in the legend. That was
    # [EN] right then (the user asked to "draw the roads in a more obvious way" on 2026-10-22) but
    # [EN] the direction is now wrong -- keeping them would not "protect" the product, it would force
    # [EN] it to misbehave. => Inverted: no road band indoors, and no "road" entry in the legend.
    # [EN] ⚠ Still judged by **shape** (outer wall-coloured >=5 plus inner paper-coloured >=3 on the
    # [EN] same coordinates), not by implementation constants like `ROAD_OUTER` -- those are gone, and
    # [EN] "add them back at another width" is exactly what a criterion should stop.
    def _road_bands(seq) -> int:
        wall = str(FP.PALETTE.get('wall', '')).lower()
        paper = str(FP.PALETTE.get('paper', '')).lower()
        seg: dict = {}
        for x in seq:
            if not isinstance(x, fcv.Line):
                continue
            pnt = getattr(x, 'paint', None)
            if pnt is None:
                continue
            col = str(getattr(pnt, 'color', '') or '').lower()
            if col not in (wall, paper):
                continue
            key = (round(float(x.x1), 1), round(float(x.y1), 1),
                   round(float(x.x2), 1), round(float(x.y2), 1))
            seg.setdefault(key, []).append(
                (col, float(getattr(pnt, 'stroke_width', 0) or 0)))
        n = 0
        for rows in seg.values():
            if any(c == wall and w >= 5.0 for c, w in rows) and \
                    any(c == paper and w >= 3.0 for c, w in rows):
                n += 1
        return n

    _bands_in = _road_bands(shapes)
    ok('D4b2 ★★★ 室内图**一条路带都没有**（这份布局有 3 条 links，一条都不许画）'
       '—— 平面图表达墙内的空间关系，道路是室外设施',
       _bands_in == 0, f'{_bands_in} 条路带')

    _leg = [v for _k, v in FP.legend_items(_det8)]
    ok('D4b3 ★★★ 室内图例里**没有"道路"这一条**'
       '（图例写着图上没有的记号，比不写更糟）',
       not any(k == 'road' for k, _v in FP.legend_items(_det8)), str(_leg))

    # ══════════════════════════════════════════════════════════════
    #  D4c ★★★ 门：**小的、不占地方**（用户 2026-10-22）
    #
    #  用户原话：「门现在画的太大 太难看了 换一种小的不占用空间的画法」。
    #  量出来的事实（改之前）：`dw = min(46, 房宽*0.42)`，开合弧 `Arc(dx0, y1-dw, dw, dw*2)`
    #  ⇒ 外接 **46 × 92 = 4232 px²**（画布的 0.75%），两个门 1.5%，弧还会**扫过房间中间**。
    #  现在：缺口宽 ≤ `DOOR_W_MAX`（18）+ **一条门扇线**（18×1.3 的笔画），
    #  占 ~18×18 px²（0.057%），只有原来的 8%，且完全贴墙。
    #
    #  ⚠ 判据要判**面积上限**，不能只判"有个门"：上一版也有门，而且很显眼。
    #  ⚠ 图形上不许再有 `Arc`（开合弧就是"大"的来源）。
    # [EN] D4c: doors must be **small and space-saving** (user, 2026-10-22: "the doors are drawn too
    # [EN] big and too ugly; use a smaller style that doesn't take up space").
    # [EN] Measured before: `dw = min(46, width*0.42)` with a swing arc of `dw x dw*2` => a 46x92
    # [EN] bounding box = 4232 px² (0.75% of the canvas), two doors 1.5%, and the arc swept through
    # [EN] the middle of the room. Now: an opening no wider than `DOOR_W_MAX` (18) plus **one leaf
    # [EN] line**, ~18x18 px² (0.057%) -- 8% of the old area, hugging the wall.
    # [EN] ⚠ Judge an **area ceiling**, not "there is a door" -- the old version had doors, very
    # [EN] visible ones. ⚠ No `Arc` may remain on the map (the swing arc is what made it big).
    # ══════════════════════════════════════════════════════════════
    _arcs = [s for s in shapes if type(s).__name__ == 'Arc']
    ok('D4c ★★★ 图上一个**开合弧都没有**（那是"门画得太大"的来源；'
       '用户：「换一种小的不占用空间的画法」）',
       not _arcs, f'Arc {len(_arcs)} 个')

    _gap = [x for x in shapes if isinstance(x, fcv.Line)
            and abs(float(getattr(getattr(x, 'paint', None), 'stroke_width', 0) or 0)
                    - (FP.WALL_T * 2 + 1.0)) < 0.01]
    _gap_len = []
    for x in _gap:
        _gap_len.append(abs(float(getattr(x, 'x2', 0)) - float(getattr(x, 'x1', 0))))
    ok('D4c2 ★★★ 门缺口**不超过 {w:g}px**（旧 46）—— 门不再占掉房间半面墙'.format(
        w=FP.DOOR_W_MAX),
       bool(_gap) and max(_gap_len) <= FP.DOOR_W_MAX + 0.01,
       f'{len(_gap)} 处 · 最宽 {max(_gap_len) if _gap_len else 0:.1f}px')

    _leaf = [x for x in shapes if isinstance(x, fcv.Line)
             and abs(float(getattr(getattr(x, 'paint', None), 'stroke_width', 0) or 0)
                     - 1.3) < 0.01]
    ok('D4c3 ★★ 每处缺口配**一条门扇线**（不是扇形）—— 记号还在，但不占地方',
       len(_leaf) >= len(_gap) >= 1, f'门扇 {len(_leaf)} 条 · 缺口 {len(_gap)} 处')

    # ③ 比例尺是一段**带刻度的尺**（不是一句 "1:100"）
    # [EN] ③ The scale bar is a **graduated ruler** (not a sentence saying "1:100")
    cell = [r for r in _rects(shapes)
            if r.width and abs(float(r.width) - FP.SCALE_CELL_W) < 2
            and r.height and abs(float(r.height) - 9.0) < 2]
    ok('D5 ★★ 比例尺画成了**一段一格一格的尺**'
       '（`0 1 2 3 4` 那串数字也在），而不是一句"1:100"',
       len(cell) >= FP.SCALE_CELLS and all(str(i) in texts for i in range(FP.SCALE_CELLS)),
       f'格子 {len(cell)} 个')

    # ══════════════════════════════════════════════════════════════
    #  D5b ★★★ 比例尺那一块**下面不许透出底纹**
    #
    #  用户 2026-10-22：「**大地图的比例尺被挡住了**」。
    #  实测的真相（不是"图压住了它"——比例尺是最后画的，永远在最上层）：
    #  底纹铺满整张画布，于是
    #    · 一条横线正好落在 `y = 576`，**那是刻度字「0 1 2 3 4」所在的那一行**，
    #      数字被一根细线当头穿过；
    #    · 一串竖线从画布顶拉到画布底，穿过比例尺标题、尺身，也穿过左上角的图例。
    #  ⇒ 判据量的是**底纹线**与**比例尺外接矩形**相不相交。
    #  ⚠ 只判"有比例尺 / 有刻度字"（D2/D5 已经那样判了）**永远绿** ——
    #    那两条在出事那天就是绿的。
    # [EN] D5b: **no underlay may show through the scale block.**
    # [EN] The user on 2026-10-22: "**the big map's scale bar is covered**". The measured truth (it is
    # [EN] not "the map drew over it" -- the scale is drawn last and is always on top): the grid covered
    # [EN] the whole canvas, so a horizontal line landed exactly on `y = 576`, **the row of the
    # [EN] graduations "0 1 2 3 4"**, striking through the digits; and vertical lines ran top-to-bottom
    # [EN] across the scale title, the ruler, and the top-left legend.
    # [EN] => The criterion measures whether **grid lines** intersect the **scale block's bbox**.
    # [EN] ⚠ Judging "there is a scale / there are graduations" (already D2/D5) is **always green** --
    # [EN] both were green on the day the user reported this.
    # ══════════════════════════════════════════════════════════════
    # ★★★ 2026-10-24：比例尺**搬到图例下面**了（用户：「大地图比例尺又被挡住了
    #   请把比例尺后续就放到图例的下面」）。所以这个框不再从"画布底"倒推，
    #   而是走产品那一份 `scale_origin()` —— 判据自己算一遍就等于两套口径。
    # [EN] ★★★ 2026-10-24: the scale bar **moved below the legend** (the user: "the big map's scale
    # [EN] bar is covered again -- from now on put it below the legend"). So this box is no longer
    # [EN] derived from the canvas bottom; it goes through the product's `scale_origin()` -- a criterion
    # [EN] computing it again would be a second definition.
    _grid_color = str(FP.PALETTE.get('grid', ''))
    _sx, _sby = FP.scale_origin(_det)
    _scale_box = (_sx - 2, _sby - 13,
                  _sx + FP.SCALE_CELLS * FP.SCALE_CELL_W + 2,
                  _sby + 9 + 12)
    _crossing = []
    _full_height = 0
    for s in shapes:
        if not isinstance(s, fcv.Line):
            continue
        if str(getattr(getattr(s, 'paint', None), 'color', '')) != _grid_color:
            continue
        _bb = (min(float(s.x1), float(s.x2)), min(float(s.y1), float(s.y2)),
               max(float(s.x1), float(s.x2)), max(float(s.y1), float(s.y2)))
        if not (_bb[2] <= _scale_box[0] or _scale_box[2] <= _bb[0]
                or _bb[3] <= _scale_box[1] or _scale_box[3] <= _bb[1]):
            _crossing.append(_bb)
        if _bb[1] <= 0 and _bb[3] >= float(FP.H):
            _full_height += 1
    ok('D5b ★★★ 比例尺那一块**底下不透底纹**（底纹收在绘图区里，'
       '不再有一条线正好穿过刻度字「0 1 2 3 4」的腰）—— 用户 2026-10-22：'
       '「大地图的比例尺被挡住了」',
       not _crossing and _full_height == 0,
       f'穿过比例尺的底纹线 {len(_crossing)} 条 · 仍铺满画布高度的竖线 {_full_height} 条')

    # ④ 右上角关闭按钮
    # [EN] ④ Top-right close button
    tree = ast.parse(src)
    has_closer = False
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == 'mk_icon_btn' and n.args):
            a0 = n.args[0]
            if (isinstance(a0, ast.Attribute) and a0.attr == 'CLOSE'
                    and float(getattr(n, 'lineno', 0)) > 0):
                seg = ast.get_source_segment(src, n) or ''
                if 'pop_dialog' in seg:
                    has_closer = True
    # ⚠ 2026-10-12 改口径（用户第四轮）：「大地图右上角 **2 个关闭按钮**
    #   **留外面的一个就行 红底的关闭按钮去掉**」。
    #   ⇒ 图上**不再叠**那个（`mk_icon_btn` 默认底色看着是红底），
    #     保留**对话框自带的 ×**（判据 F2b 在 `verify_plan_geometry` 里）。
    # [EN] ⚠ Convention changed on 2026-10-12 (the user's fourth round): "there are **2 close buttons
    # [EN] in the big map's top-right**; **keep just the outer one -- remove the red-background one**".
    # [EN] ⇒ the overlaid one is **gone** (`mk_icon_btn`'s default background reads as red) and the
    # [EN] **dialog's own x** stays (criterion F2b lives in `verify_plan_geometry`).
    ok('D6 ★★★ 大地图**不再在图上叠关闭按钮**（用户第四轮：「留外面的一个就行 '
       '红底的关闭按钮去掉」）—— 对话框自带的 × 留着（见 `verify_plan_geometry` 的 F2b）',
       not has_closer, f'图上还叠着={has_closer}')

    # ⑤ 街道图的大画法：**只标记建筑**（不出现室内记号）
    #
    # ★★ 2026-10-27 口径改：原来断言"`legend_items('整体')` 里有'街道'、没有'房间墙'"。
    #   而 `legend_items('整体')` 现在**返回空表** —— 城市/城际/甲板各有自己的图例
    #   （右下角），左边再列一套会出现两套互相矛盾的说明（详见 `legend_items` 的说明）。
    #   ⇒ 这条要防的东西**还在**：街道图不许把室内那套（房间墙 / 屋内陈设 / 院子）带上图。
    #     所以改为**直接查图元与文字**：没有 `wall_hi` 色的墙、文字里没有"房间墙/屋内陈设"。
    #   ⚠ 比原来更严：原来只查图例文字（图例不列 ≠ 图上不画），现在查图上真画了什么。
    # [EN] ★★ 2026-10-27 change of reading: it used to assert "`legend_items('整体')` contains
    # [EN] 'street' and no 'room wall'". That table now returns **empty** -- city / region / deck each
    # [EN] have their own legend in the bottom-right, and a second set on the left would contradict it
    # [EN] (see the note in `legend_items`). => What this guarded **still matters**: a street map must not
    # [EN] carry the indoor marks. So it now checks **the primitives and text directly**: no wall stroke
    # [EN] in `wall_hi`, and no "room wall / indoor fixtures" in the text. ⚠ Stricter than before: it
    # [EN] used to read the legend (not listing is not the same as not drawing).
    st = FP.build_detail_shapes(street(), place='某某镇', when='第 4 天')
    st_texts = _texts(st)
    has_wall = any(str(getattr(getattr(s, 'paint', None), 'color', '')).lower()
                   == str(FP.PALETTE.get('wall_hi', '')).lower() for s in st)
    ok('D7 ★★★ 街道图（很大那种）**不画室内布置**：图上没有室内墙色、'
       '文字里没有"房间墙/屋内陈设"',
       not has_wall
       and not any(('房间墙' in x or '屋内陈设' in x or '院子（露天）' in x) for x in st_texts)
       and bool([x for x in st_texts if x]),
       f'室内墙={has_wall} · 文字={[x for x in st_texts if x][:6]}')
    rep['street_texts'] = [x for x in st_texts if x][:10]

    # ⑥ 画法：室内图上**墙是双线、门有门洞**（照规矩画，不是写个"门"字）
    # [EN] ⑥ Drawing: on an indoor map **walls are double lines and doors get an opening** (drawn by
    # [EN] convention, not the word "door")
    #
    # ⚠⚠ 2026-10-22：这条判据原来守的是「**门有开合弧**」（标准平面图的扇形记号）。
    #   用户当轮原话：「门现在画的太大 太难看了 换一种小的不占用空间的画法」
    #   —— **弧本身就是他要去掉的那个东西**（46×92 = 画布 0.75%，还扫过房间中间）。
    #   所以这条判据守的**已是被推翻的设计**：不改它，产品照用户要求改完它就恒红；
    #   删掉它，"门有没有照规矩画"就没人守了。
    #   ⇒ 改口径：仍然守"门的记号存在且是画出来的"，但记号换成**新的那一种**
    #     （缺口 + 门扇线）。⚠ 这不是"放宽判据" —— D4c 另有面积/弧的上限在守，
    #     而且"缺口配门扇"是一条更具体的要求（两条线、方向朝房间内）。
    # [EN] ⚠⚠ 2026-10-22: this criterion used to guard "**doors have swing arcs**" (the fan symbol
    # [EN] from standard floor plans). The user's words that round: "the doors are drawn too big and
    # [EN] too ugly; use a smaller style that doesn't take up space" -- **the arc itself is what he
    # [EN] wanted gone** (46x92 = 0.75% of the canvas, sweeping through the room). So the criterion
    # [EN] was guarding **a design that had been overturned**: leave it and the product goes
    # [EN] permanently red after the requested change; delete it and nothing guards "doors are drawn
    # [EN] by convention" at all.
    # [EN] => Keep the intent ("the door mark exists and is drawn"), with the **new** mark
    # [EN] (opening + leaf line). ⚠ This is not loosening -- D4c separately caps the area and bans
    # [EN] arcs, and "an opening paired with a leaf" is a more specific requirement (two lines, leaf
    # [EN] pointing into the room).
    _gap8 = [x for x in shapes if isinstance(x, fcv.Line)
             and abs(float(getattr(getattr(x, 'paint', None), 'stroke_width', 0) or 0)
                     - (FP.WALL_T * 2 + 1.0)) < 0.01]
    _leaf8 = [x for x in shapes if isinstance(x, fcv.Line)
              and abs(float(getattr(getattr(x, 'paint', None), 'stroke_width', 0) or 0)
                      - 1.3) < 0.01]
    _into_room = 0
    for x in _leaf8:
        # 门扇朝房间内 = 终点 y 比缺口那头**小**（图上房间在墙上方）
        if float(getattr(x, 'y2', 0)) < float(getattr(x, 'y1', 0)) - 0.01:
            _into_room += 1
    ok('D8 ★★ 门画成了**缺口 + 门扇线**（照规矩画，不是写个"门"字），'
       '而且**门扇朝房间内**—— 2026-10-22 起不再用开合弧（用户嫌它大）',
       bool(_gap8) and len(_leaf8) >= len(_gap8) and _into_room >= 1,
       f'缺口 {len(_gap8)} · 门扇 {len(_leaf8)} · 朝内 {_into_room}')

    # ⑦ 对话框真的被接到小地图上了（点了会调它）
    # [EN] ⑦ The dialog is really wired to the minimap (clicking calls it)
    ok('D9 ★★★ 左栏小地图**点了会打开它**（画布外面包了 `GestureDetector`，'
       '指向 `show_map_dialog`）',
       'GestureDetector' in src and 'self.show_map_dialog()' in src, '')
    ok('D10 ★ 而且鼠标是**手型**（不然用户看不出来它能点 = 等于没做）',
       'MouseCursor.CLICK' in src, '')

    # ⑧ 信息框里的**时间**：与左栏「时间」面板**同一个来源**（`world.clock_display()`），
    #    拿不到就留空、**绝不编一个时刻**。
    # [EN] ⑧ The **time** in the info box: **the same source** as the left column's "Time" panel
    # [EN] (`world.clock_display()`); when unavailable it stays blank and **never invents a moment**.
    from gui.app_flet import NovelWorldApp
    from types import SimpleNamespace
    shell = NovelWorldApp.__new__(NovelWorldApp)
    shell._map_world = SimpleNamespace(clock_display=lambda: '第 3 天 · 戌时')
    got = shell._map_when_text()
    shell._map_world = None
    empty = shell._map_when_text()

    def _boom():
        raise RuntimeError('x')
    shell._map_world = SimpleNamespace(clock_display=_boom)
    threw = shell._map_when_text()
    rep['when'] = {'ok': got, 'none': empty, 'boom': threw}
    ok('D11 ★★ 信息框的「时间」取自 `world.clock_display()`'
       '（与左栏时间面板同源），拿不到 / 出异常都**留空不编**',
       got == '第 3 天 · 戌时' and empty == '' and threw == '', str(rep['when']))


# ══════════════════════════════════════════════════════════════════════
#  E 本地存档与复用
# [EN] E local archive and reuse
# ══════════════════════════════════════════════════════════════════════
def test_store() -> None:
    rep = {}
    tmp = Path(tempfile.mkdtemp(prefix='nws_mapstore_'))
    try:
        class _P:
            pass
        p = _P()
        p.root = tmp
        lay = tea_house()
        basis = MS.basis_of('室内', ['堂屋', '井'], '堂屋')
        saved = MS.save(p, '室内', '临河茶肆', lay, basis=basis)
        rep['saved'] = MS.saved(p)
        ok('E1 ★★★ 地图**存得进本地**（`<项目>/地图/*.json`）'
           '—— 用户：「所有的地图保存在本地」',
           saved and (Path(tmp) / MS.DIRNAME).is_dir()
           and len(MS.saved(p)) == 1, str(rep['saved']))

        got = MS.reuse(p, '室内', '临河茶肆', basis)
        rep['reuse'] = bool(got)
        ok('E2 ★★★ 同一局面**复用得回来**（用户：「如果后续场景能够复用的话则直接复用」）'
           '—— 且**没花模型调用**',
           got is not None and len(got.places) == len(lay.places)
           and got.frame == '临河茶肆', str(rep['reuse']))

        # ★★★ 2026-10-26 **口径改了（设计被用户推翻，不是放宽）**：
        #   用户原话：「小地图和大地图 每次生成的感觉都有一些区别 有办法在整个小说推演
        #   过程中维持相同场景地图的一致性吗」。
        #   旧口径是"今天地点集合变了 ⇒ 该重画"，而"一天演几处地方"本是常态
        #   ⇒ 这条判据守的行为等于"几乎每天都重画" ⇒ **正是用户抱怨的那件事**。
        #   新口径（成对，缺一条就漏一类）：
        #     ① 同一层、同一处主地点，**地点集合变了也要复用**（新地点由
        #        `image_gen.mapanchor.fill()` 补进旧图，老的一处都不动）；
        #     ② **换了主地点 / 换了层**才该重画 —— 否则走到别的城市还是这张图。
        #   ⚠ ① 不许把 ② 一起吃掉：只剩 ① 就是"永远复用一张图"。
        # [EN] ★★★ 2026-10-26 **the criterion changed (a design the user overturned, not a
        # [EN] loosening)**: the user asked "the minimap and big map feel different every time; can we
        # [EN] keep scene maps consistent across the whole simulation?". The old rule was "today's
        # [EN] place set changed => redraw", and a story visiting a few places a day is normal, so it
        # [EN] meant "redraw almost daily" -- exactly what the user complained about. The new pair:
        # [EN] ① same layer and same main place => **reuse even when the place set changed** (new
        # [EN] places are added to the old map by `image_gen.mapanchor.fill()`, nothing old moves);
        # [EN] ② **a different main place or layer** must miss -- otherwise the map of one city
        # [EN] follows you to another. ⚠ ① must not swallow ②: only ① would mean "reuse one map
        # [EN] forever".
        other = MS.basis_of('室内', ['堂屋', '后院'], '堂屋')
        rep['mismatch'] = MS.reuse(p, '室内', '临河茶肆', other)
        ok('E3 ★★★ 同一处地方、**地点集合变了也复用**（新地点补进旧图，位置一处都不动）'
           '—— 用户 2026-10-26：「每次生成的感觉都有一些区别」',
           rep['mismatch'] is not None, str(bool(rep['mismatch'])))

        rep['mismatch2'] = MS.reuse(p, '室内', '别处茶楼', MS.basis_of('室内', ['堂屋'], '别处茶楼'))
        rep['mismatch3'] = MS.reuse(p, '整体', '临河茶肆', MS.basis_of('整体', ['堂屋'], '临河茶肆'))
        ok('E3b ★★★ 成对：**换了地方 / 换了层**就不复用（否则走到别处还是这张图）',
           rep['mismatch2'] is None and rep['mismatch3'] is None,
           f"换地方={rep['mismatch2']} 换层={rep['mismatch3']}")

        # ★ 旧格式存档（`层//地点集合//这里`）要能认出来：认一次省一次模型调用，
        #   而且它本来就是**同一处地方**的图（位置由 `mapanchor` 统一）。
        # [EN] An old-format archive must be recognized: it saves one model call, and it IS the map
        # [EN] of the **same place** (positions are unified by `mapanchor`).
        _old = MS.save(p, '室内', '旧格式', lay,
                       basis='室内//堂屋/井//堂屋')
        rep['legacy'] = MS.reuse(p, '室内', '旧格式', MS.basis_of('室内', ['堂屋', '灶房'], '堂屋'))
        ok('E3c ★★ 旧格式存档（`层//地点集合//这里`）**认得出来**，不白花一次调用',
           _old and rep['legacy'] is not None, str(bool(rep['legacy'])))

        # ⚠ 存档是**旁路**：坏掉/没有时**不许抛**（推演不该因为存档挂掉）
        # [EN] ⚠ The archive is a **bypass**: when broken/absent it **must not throw** (the simulation
        # [EN] must not die because of an archive)
        class _Bad:
            pass
        bad = _Bad()
        bad.root = Path('Z:/根本没有这个盘/xx')
        ok('E4 ★ 存档目录不可用时**返回假/None 而不抛**（失败只记日志）',
           MS.save(bad, '室内', 'x', lay) is False
           and MS.reuse(bad, '室内', 'x', basis) is None,
           '')
        ok('E5 ★ 存档**只在项目下**（`<项目>/地图/`），不碰运行文件夹以外的任何地方',
           MS.DIRNAME == '地图' and 'DIRNAME' in inspect.getsource(MS.dir_of), '')

        # ⚠⚠ **`Path` 也有 `.root` 属性**（`Path('C:/a/b').root` = 盘根）——
        #    `dir_of()` 要是先 `getattr(project,'root',project)`，传进来一个
        #    `Path` 就会拿到**盘根**，存档写到 `C:/地图/` 去。
        #    ★ 这一条**不是假设**：E6b 当初就是因此"第一次就复用上了"，
        #      从而抓出文件被写到了盘根（本项目第二次踩这个坑）。
        # [EN] ⚠⚠ **`Path` also has a `.root` attribute** (`Path('C:/a/b').root` = the drive root) --
        # [EN]   if `dir_of()` does `getattr(project,'root',project)` first, a `Path` argument yields
        # [EN]   the **drive root** and the archive lands in `C:/地图/`.
        # [EN]   ★ This is **not hypothetical**: it is why E6b's first call "reused" something --
        # [EN]     which exposed that the file had been written to the drive root (the second time this
        # [EN]     project has hit this trap).
        probe = Path(tempfile.mkdtemp(prefix='nws_dirprobe_'))
        try:
            got = MS.dir_of(probe)
            rep['dir_of'] = str(got)
            ok('E5b ★★★ 传一个 **`Path`** 进去得到的是"那个目录/地图"，'
               '**不是盘根**（`Path` 也有 `.root`，会被 `getattr` 骗到）',
               got == probe / MS.DIRNAME,
               f'得到 {got}（期望 {probe / MS.DIRNAME}）')
        finally:
            shutil.rmtree(probe, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 接线：主循环真的调了它
    # ⚠ **不能查字符串**（`'MSTORE.reuse(' in src`）—— 反例法当场抓出过这条：
    #   把 `_draw_day_map` 里那次调用改成 `_reuse = None`，字符串还在
    #   （它在 `_day_map_reuse` 的函数体里），判据照样绿。
    #   ⇒ 改成 **AST 判"`_draw_day_map` 的方法体里有没有这两个调用"**，
    #     再 **行为判**"这两个方法真的存得进、复用得回"。
    # [EN] Wiring: the main loop really calls it.
    # [EN] ⚠ **Do not check strings** (`'MSTORE.reuse(' in src`) -- the counterexample method caught
    # [EN] this: changing that call in `_draw_day_map` to `_reuse = None` leaves the string present
    # [EN] (it is inside `_day_map_reuse`'s body) and the criterion stays green.
    # [EN] ⇒ Switch to an **AST check "does `_draw_day_map`'s own body call these two"** plus a
    # [EN] **behavioral check** "do those two methods really save and reuse".
    loop_src = _txt('sim/loop.py')
    tree = ast.parse(loop_src)
    body_calls: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == 'RunLoop':
            for sub in n.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == '_draw_day_map':
                    for c in ast.walk(sub):
                        if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                                and c.func.attr in ('_day_map_reuse', '_day_map_save')):
                            body_calls.add(c.func.attr)
    ok('E6a ★★★ `_draw_day_map` 的方法体里**真的调了**"先试复用"与"画完存一份"'
       '（AST 判 —— 查字符串会被函数体里的另一份骗过去）',
       body_calls == {'_day_map_reuse', '_day_map_save'}, str(sorted(body_calls)))

    # ★ 行为判：拿一个**真的主循环对象**（`__new__` 壳）调那两个方法，
    #   看它到底有没有落到存档上。
    # [EN] ★ Behavioral check: call those two methods on a **real loop object** (a `__new__` shell) and
    # [EN] see whether they really hit the archive.
    from sim.loop import RunLoop
    tmp2 = Path(tempfile.mkdtemp(prefix='nws_loopstore_'))
    try:
        from types import SimpleNamespace
        shell = RunLoop.__new__(RunLoop)
        shell.runfolder = SimpleNamespace(project_dir=tmp2)
        shell.day_map = None
        shell.world = SimpleNamespace(day_map=None)
        shell._log_day_map = lambda *a, **k: None
        layers = [('室内', '临河茶肆', tea_house())]
        first = shell._day_map_reuse(layers, ['堂屋', '井'], '堂屋',
                                     SimpleNamespace(day=1))
        shell._day_map_save(layers, ['堂屋', '井'], '堂屋', tea_house())
        second = shell._day_map_reuse(layers, ['堂屋', '井'], '堂屋',
                                      SimpleNamespace(day=1))
        rep['behav'] = {'first': first, 'second': second}
        ok('E6b ★★★ 行为级：第一次**没得复用**（返回 None），存过之后**第二次复用得到**'
           '（这就是"后续场景直接复用"真的成立）',
           first is None and second is True, str(rep['behav']))
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
def main() -> int:
    print('═' * 62)
    print('  验证：地图细致程度分档 + 室内画墙 + 大地图 + 本地复用')
    print('═' * 62)
    try:
        print('\n【A】细致程度（纯函数）')
        test_detail()
        print('\n【B】红点没了 + 室内画墙')
        test_walls()
        print('\n【C】kind/frame 往返不丢')
        test_roundtrip()
        print('\n【D】大地图对话框')
        test_big_map()
        print('\n【E】本地存档与复用')
        test_store()
    except Exception:                                            # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(traceback.format_exc(), flush=True)

    bad = [c for c in report['checks'] if not c['ok']]
    report['passed'] = len(report['checks']) - len(bad)
    report['total'] = len(report['checks'])
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'map_detail_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  地图细致程度验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62, flush=True)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
