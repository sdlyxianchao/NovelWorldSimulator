# -*- coding: utf-8 -*-
"""验证：小图 LOD（比大图简略一级，但**按地图标准绘制**，四种级别各有不同样子）。

用户 2026-10-16（两则消息合并）
------------------------------
①「小地图比大地图画的内容简略一个级别」「小地图就把房子或者房子以上的东西画好
   就可以 内部夹具太小了可以不带 如果是更大的地图 比如城市 那小地图就把城市本身和
   周围的东西画好就行 大地图才会画城市里的街道」

②「地图是要按照地图标准绘制 根据级别 可能包含
   室内地图 / 室内外地图（单个住宅或者几个住宅的室内和室外）/
   街區地图（或者村庄）若干房屋 街道和附近内容 / 跨城市地图（若干城市和他们附近的内容）
   这几种级别都要绘制不同的样子 要用不同的绘制方式和内容
   并且保持之前要求的限制 比如不要带红色圆圈 建筑 城市 房子的名字尽可能不要覆盖其他内容」

⇒ 四种级别各自的画法（小图相对大图简略一级，但都按地图标准）：
  · 室内 / 室内外 → 'building'：框 + 房间墙（地图标准，必须有）+ 院子；
    屋里小家具可省（"夹具可省"）；**不画房间墙是错误的**（那违背地图标准）。
  · 街区 / 村庄（局部）→ 'area'：若干房屋 + 街道 + 附近（地点小字 + 通路 + 水系）。
  · 跨城市（整体）→ 'city'：画**城市轮廓 + 周围**，不画街道网
    （街道网留给大地图；"大地图才会画城市里的街道"）。
  · 任何级别都**没有实心红圆**（用户反复要求）。

判据纪律（反例法配套见 developers/mutate_minimap_lod.py）
--------------------------------------------------------
  · 纯逻辑：不依赖 flet 窗口，直接 `from image_gen import minimap as MM`。
  · 每条都钉"真行为"，不是源码哨兵。
  · 城市轮廓用 `fcv.Path`（不是 `fcv.Rect`），免得被"非室内不加框"那条误抓。

跑法：.venv\\Scripts\\python.exe tools/verify_minimap_lod.py
产出：assets/screenshots/minimap_lod_report.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import flet.canvas as fcv                              # noqa: E402
from image_gen import minimap as MM                    # noqa: E402
from image_gen.map_layout import Layout, Place        # noqa: E402

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

checks: list = []


def ok(name: str, cond, detail='') -> bool:
    checks.append({'name': name, 'ok': bool(cond),
                   'detail': str(detail)[:200]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f"   [{detail}]" if not cond else ''))
    return bool(cond)


# ── 夹具 ──
def indoor() -> Layout:
    return Layout(
        places=[Place('门', 0.5, 0.9, shape='门'),
                Place('前厅', 0.5, 0.72, shape='屋'),
                Place('堂屋', 0.5, 0.48, shape='屋'),
                Place('天井', 0.72, 0.24, shape='院'),
                Place('井', 0.86, 0.3, shape='院'),
                Place('后院', 0.5, 0.14, shape='院')],
        kind='室内', frame='临河茶肆', caption='临河茶肆')


def inout() -> Layout:
    return Layout(
        places=[Place('门', 0.5, 0.9, shape='门'),
                Place('前厅', 0.5, 0.72, shape='屋'),
                Place('堂屋', 0.5, 0.48, shape='屋'),
                Place('天井', 0.72, 0.24, shape='院'),
                Place('井', 0.86, 0.3, shape='院'),
                Place('后院', 0.5, 0.14, shape='院')],
        kind='室内外', frame='临河茶肆', caption='临河茶肆')


def block() -> Layout:
    return Layout(
        places=[Place('临河茶肆', 0.3, 0.4, shape='楼'),
                Place('北门市集', 0.7, 0.6, shape='市'),
                Place('城东渡口', 0.85, 0.8, shape='渡')],
        kind='局部', caption='临河镇',
        links=[{'a': '临河茶肆', 'b': '北门市集', 'kind': '路'},
               {'a': '北门市集', 'b': '城东渡口', 'kind': '路'}],
        walls=[[0.1, 0.2], [0.9, 0.2], [0.9, 0.9], [0.1, 0.9], [0.1, 0.2]])


def city() -> Layout:
    return Layout(
        places=[Place('临河镇', 0.2, 0.3, shape='市'),
                Place('云栖城', 0.8, 0.4, shape='市'),
                Place('南屏县', 0.5, 0.85, shape='县')],
        kind='整体', caption='三城志',
        links=[{'a': '临河镇', 'b': '云栖城', 'kind': '路'},
               {'a': '云栖城', 'b': '南屏县', 'kind': '路'}],
        # ★ 街道网（一堆折线）—— 跨城市小图**不该**画它，留给大图
        # [EN] street network (a bunch of polylines) -- the cross-city minimap
        # [EN] must NOT draw it; that is the big map's job.
        walls=[[0.05, 0.1], [0.95, 0.1], [0.95, 0.95], [0.05, 0.95],
               [0.05, 0.1], [0.5, 0.1], [0.5, 0.95]])


def _rects(shapes):
    return [s for s in shapes if isinstance(s, fcv.Rect)]


def _paths(shapes):
    return [s for s in shapes if isinstance(s, fcv.Path)]


def _texts(shapes) -> list[str]:
    return [str(getattr(s, 'value', '') or '') for s in shapes
            if type(s).__name__ == 'Text']


def _path_points(p) -> list[tuple[float, float]]:
    """取一个 `fcv.Path` 的所有顶点（MoveTo / LineTo）。

    ⚠ flet 的 `Path` 把段存在 `.elements`（不是 `.segments`）。
    [EN] ⚠ flet's `Path` stores segments in `.elements` (not `.segments`).
    """
    pts: list[tuple[float, float]] = []
    for seg in getattr(p, 'elements', None) or []:
        xs = getattr(seg, 'x', None)
        ys = getattr(seg, 'y', None)
        if xs is None or ys is None:
            continue
        try:
            pts.append((round(float(xs), 1), round(float(ys), 1)))
        except (TypeError, ValueError):
            pass
    return pts


def _pos_pixels(lay, W=196, H=132, pad_x=16, pad_y=15):
    return {p.name: (pad_x + p.x * (W - 2 * pad_x),
                     pad_y + p.y * (H - 2 * pad_y - 8))
            for p in lay.places}


# ══════════════════════════════════════════════════════════════════════
def test_lod_mapping() -> None:
    """L1 `minimap_lod` 把大图档位映射到正确的小图档位（纯函数，同输入同输出）。"""
    cases = [
        ('室内', indoor(), 'building'),
        ('室内外', inout(), 'building'),
        ('街区/村庄（局部）', block(), 'area'),
        ('跨城市（整体）', city(), 'city'),
    ]
    got = {label: MM.minimap_lod(lay) for label, lay, _ in cases}
    bad = [label for label, _, want in cases if got[label] != want]
    ok('L1a ★★★ 四种大图档位 → 正确的小图档位'
       '（室内/室内外→building，局部→area，整体→city）',
       not bad, f'错={[(label, got[label]) for label, _, _ in cases if label in bad]}')

    # 纯函数：同输入永远同输出
    stab = {MM.minimap_lod(city()) for _ in range(5)}
    ok('L1b ★★ 同一份布局每次判出同一档位（纯函数）', len(stab) == 1, str(stab))


def test_city() -> None:
    """L2 跨城市小图：画城市轮廓 + 周围，不画街道网。"""
    lay = city()
    sh = MM.build_shapes(lay, current='临河镇')
    paths = _paths(sh)
    texts = _texts(sh)
    pos = _pos_pixels(lay)

    # ① 城市档**不画**"地点凸包"这种自由多边形。
    #
    # ★★★ 2026-10-27 口径反转（用户：「小地图效果是**一些不规则图形**」）。
    #   这里原来断言"存在一条顶点集 = 城市点凸包的 Path"，那是 2026-10-16 的设计。
    #   用户的否定说明那个设计本身错了：凸包既不是城墙也不是城市边界 ——
    #   它随地点个数变形、没有任何数据依据，还会连出一条"包住所有点"的边让读者
    #   以为那是环路。所以现在**断言没有**这种多边形。
    #   ⚠ 这条判据原来要防的东西**还在**：别在小图上画街道网/房间墙（下面 L2b 仍在测）。
    #     换的只是"证据"——从"有凸包"换成"没有自由多边形 + 路按等级"。
    # [EN] ① The city tier draws **no** free-form "location hull" polygon. ★★★ Reversed 2026-10-27
    # [EN] (the user: "the minimap shows **some irregular shapes**"). This used to assert a Path whose
    # [EN] vertex set equalled the hull of the city points (the 2026-10-16 design). The user's
    # [EN] rejection shows the design itself was wrong: a hull is neither a wall nor a city boundary --
    # [EN] it warps with the number of points, has no data behind it, and draws an edge "wrapping all
    # [EN] points" that reads as a ring road. So it now asserts the **absence** of such a polygon.
    # [EN] ⚠ What this criterion guarded is **still guarded**: no street network / room walls on the
    # [EN] minimap (L2b below). Only the *evidence* changed.
    exp_hull = set((round(x, 1), round(y, 1))
                   for x, y in MM._convex_hull(list(pos.values())))
    hull_like = [p for p in paths
                 if len(_path_points(p)) >= 3
                 and set(_path_points(p)) == exp_hull]
    free_polys = [p for p in paths if len(_path_points(p)) >= 3]
    ok('L2a ★★★ 跨城市小图**不画**"地点凸包"（那就用户说的"不规则图形"：'
       '它随地点个数变形、没有数据依据、还会被读成环路）',
       not hull_like and not free_polys,
       f'paths={len(paths)} 凸包={len(hull_like)} 自由多边形={len(free_polys)}')

    # ② 街道网**不画**：把 `layout.walls` 变换成像素点集，图上不应存在与之重合的 Path。
    # [EN] ② The street network is **not drawn**: transform `layout.walls` to pixel points and
    # [EN] assert no Path on the map matches it.
    W, H, pad_x, pad_y = 196, 132, 16, 15
    net = set()
    for x, y in lay.walls:
        net.add((round(pad_x + x * (W - 2 * pad_x), 1),
                 round(pad_y + y * (H - 2 * pad_y - 8), 1)))
    net_drawn = any(net.issubset(set(_path_points(p))) for p in paths)
    ok('L2b ★★★ 跨城市小图**不画街道网**（街道网留给大图）',
       not net_drawn, f'街道网点集被画出来={net_drawn}')

    # ③ 每个城市名都写出来（"把城市本身和周围的东西画好"）。
    # [EN] ③ Every city name is written out ("draw the city itself and what is around it").
    ok('L2c 跨城市小图把每个城市名都标了出来',
       all(n in texts for n in ('临河镇', '云栖城', '南屏县')), str(texts)[:80])

    # ④ 没有实心红圆（用户铁律）。
    # [EN] ④ No filled red circle (the user's hard rule).
    n_circ = sum(1 for s in sh if type(s).__name__ == 'Circle')
    ok('L2d ★★★ 跨城市小图一个实心圆都没有', n_circ == 0, f'圆 {n_circ} 个')


def test_building() -> None:
    """L3 室内/室内外小图：保留房间墙（地图标准），无实心圆。"""
    for label, lay in (('室内', indoor()), ('室内外', inout())):
        sh = MM.build_shapes(lay, current='堂屋')
        rects = _rects(sh)
        # 房间墙：宽 > 50 且高 > 40 的矩形（排除建筑外框 x≈6）。
        # ⚠ 用**绝对下限**，不拿 `MM.ROOM_MIN_W` 比（那是自证陷阱）。
        # [EN] Room walls: rects wider than 50 and taller than 40 (excluding the frame at x≈6).
        # [EN] ⚠ Absolute lower bound, not compared against `MM.ROOM_MIN_W` (self-proving trap).
        room = [r for r in rects if r.width and r.width > 50 and r.height
                and r.height > 40
                and abs(float(getattr(r, 'x', 0) or 0) - 6) > 2]
        n_circ = sum(1 for s in sh if type(s).__name__ == 'Circle')
        ok(f'L3a ★★★ {label}小图**保留房间墙**（地图标准：室内地图要有墙）',
           len(room) >= 1, f'房间墙 {len(room)} 块')
        ok(f'L3b ★★★ {label}小图一个实心圆都没有', n_circ == 0, f'圆 {n_circ} 个')


def test_area() -> None:
    """L4 街区/村庄（局部）小图：无整座楼大框，地点名都标出。"""
    lay = block()
    sh = MM.build_shapes(lay, current='临河茶肆')
    rects = _rects(sh)
    texts = _texts(sh)
    big = [r for r in rects if r.width and r.width >= 150
           and float(getattr(r, 'x', 0) or 0) >= 3]
    ok('L4a ★★★ 街区/村庄小图**不加整座楼大框**（那是室内图的画法）',
       not big, f'大框 {len(big)} 个')
    ok('L4b 街区/村庄小图把每个地点名都标了出来',
       all(n in texts for n in ('临河茶肆', '北门市', '城东渡')), str(texts)[:80])


def main() -> int:
    print('═' * 60)
    print('  验证：小图 LOD（四种级别，按地图标准，比大图简略一级）')
    print('═' * 60)
    try:
        test_lod_mapping()
        test_city()
        test_building()
        test_area()
    except Exception:                                            # noqa: BLE001
        import traceback
        print(traceback.format_exc())
    bad = [c for c in checks if not c['ok']]
    report = {'checks': checks, 'passed': len(checks) - len(bad),
              'total': len(checks), 'ok': not bad}
    OUT.joinpath('minimap_lod_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n  小图 LOD 验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
