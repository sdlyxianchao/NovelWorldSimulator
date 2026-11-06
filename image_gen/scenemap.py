# -*- coding: utf-8 -*-
"""**场景地图**：每换一次场景存一张大地图，导小说时按场景插进去。

用户 2026-10-22 原话（四件事，这个模块负责后面三件）
------------------------------------------------------
「场景切换的时候需要重新绘制地图 且场景切换在剧作家写作 导演导戏过程中知道
 且场景切换应该是一个明确的动作并引发地图重绘」
「所有地图（小地图和大地图）都需要按照场景保存下来」
「后续导出小说的时候每个场景都需要插入大地图并带有简单描述」

为什么存 **SVG** 而不是 PNG
---------------------------
画地图的代码只有一份：`image_gen/floorplan.build_detail_shapes()` 把一份 `Layout`
算成一串 flet 画布形状。界面上是用 `ft.canvas.Canvas(shapes)` 直接画的。
如果这里另写一个 Pillow 渲染器，那就是**两份画法** —— 改个配色、挪个标签就得改两处，
迟早出现"界面上一处、导出里另一处"（本项目的万恶之源）。

所以这里只做一件事：**把同一串形状写成 SVG**。同一份输入 ⇒ 同一个形状列表 ⇒
同一张图；界面和导出共用一次计算。

存在哪
------
`<运行文件夹>/场景地图/`
  · `第001天_第01场_望江楼.svg`  —— 图本身
  · `清单.json`                  —— 每场一条：天 / 场次 / 地点 / 时辰 / 图 / 一句话描述

⚠ 铁律（与 `llm/usage.record()`、`image_gen/mapstore` 同一条）：**失败只记日志、绝不抛**。
  存图是旁路。旁路把自己变成故障源是这类模块最常见的翻车方式（磁盘满 / 文件被占）。
  存不下时推演照跑，只是这次导出少一张图。

English:
**Scene maps**: save one big map per scene change, and insert them when exporting the novel.
The user's words on 2026-10-22 (four things; this module owns the last three): scene changes must
redraw the map, the change must be an explicit action (the playwright/director know about it), every
map must be saved per scene, and the exported novel must carry a big map plus a short description for
each scene.
Why **SVG** rather than PNG: there is exactly one drawing implementation --
`image_gen/floorplan.build_detail_shapes()` turns a `Layout` into a list of flet canvas shapes, and the
UI draws them with `ft.canvas.Canvas(shapes)`. A Pillow renderer here would be a **second drawing
implementation**, and changing a colour or moving a label would mean editing two places -- eventually
producing "one thing in the UI, another in the export". So this module does one thing only: **write
that same shape list as SVG**.
Lives in `<run>/场景地图/`: `第001天_第01场_<place>.svg` plus `清单.json` (one row per scene: day,
index, place, time label, file, one-line description).
⚠ Iron rule (same as `llm/usage.record()` and `image_gen/mapstore`): **log on failure, never throw.**
Archiving is a bypass, and a bypass that turns itself into a failure source is the classic crash.
When it cannot be written the simulation runs on; the export just has one map fewer.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from logger import get_logger

_LOG = get_logger('nws.scenemap')

#: 场景地图放在运行文件夹下的哪个子目录。
# [EN] : the sub-directory of the run folder that holds scene maps.
DIRNAME = '场景地图'

#: 清单文件名（JSON：机读；人也能读）。
# [EN] : the manifest filename (JSON: machine-readable, and still human-readable).
MANIFEST = '清单.json'

#: 清单格式版本。**改了结构就要 +1**，读回时版本对不上就当作废。
# [EN] : manifest format version. **Bump it when the structure changes**; on read-back a mismatch is
# [EN] treated as stale rather than forced through.
VERSION = 1


def dir_of(run) -> Path | None:
    """场景地图目录（**只算路径，不建目录**）。拿不到就 None。

    `run` 三种都认：`RunFolder`（取 `.root`）、`Path`、字符串 —— 调用方有两拨
    （主循环拿 `runfolder`，导出拿 `run.root`），只认一种的话另一拨会静默存不下来。
    [EN] The scene-map directory (**path only, does not create it**); None when unknown.
    [EN] `run` may be a `RunFolder` (its `.root`), a `Path`, or a string -- there are two callers
    [EN] (the loop has `runfolder`, the export has `run.root`); accepting only one makes the other
    [EN] silently fail to save.
    """
    if run is None:
        return None
    root = getattr(run, 'root', None)
    if root is None and isinstance(run, (str, Path)):
        root = run
    if root is None:
        return None
    try:
        return Path(root) / DIRNAME
    except (TypeError, ValueError):                             # noqa: BLE001
        return None


def _safe(name: str) -> str:
    """文件名里不许有路径分隔符与 Windows 保留字符。

    ⚠ 地点名是**模型写的字**，里面出现 `/`（"河岸/柳树下"）不是怪事；
      不过一遍就会出现"图存到别的目录去"或直接抛异常。
    [EN] No path separators or Windows-reserved characters in a filename.
    [EN] ⚠ Place names are **model-written text**; a `/` inside ("riverbank/under the willow") is not
    [EN] unusual, and without this pass the image lands somewhere else or the write throws.
    """
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', str(name or '').strip())
    return s.strip(' .') or '未命名'


def plate_name(day: int, index: int, place: str) -> str:
    """图的文件名：`第001天_第01场_<地点>.svg`。

    ★ 天与场次都**补零**：文件名要能按字典序排成时间序（导出、翻目录都靠它）。
    [EN] The image filename: `第001天_第01场_<place>.svg`.
    [EN] ★ Both day and scene index are **zero-padded** so the names sort lexicographically in time
    [EN] order (the export and a human browsing the folder both rely on it).
    """
    return f'第{int(day or 0):03d}天_第{int(index or 0):02d}场_{_safe(place)}.svg'


# ══════════════════════════════════════════════════════════════════
#  shapes → SVG
# ══════════════════════════════════════════════════════════════════
def _color(value) -> str:
    """flet 的颜色 → SVG 的颜色串。拿不到就 `none`（**不编一个黑色**）。"""
    s = str(value or '').strip()
    return s if s else 'none'


def _paint_attrs(paint, *, fill: bool) -> str:
    """把一个 `ft.Paint` 翻成 SVG 的属性串。

    ⚠ `ft.PaintingStyle` 只有 FILL / STROKE；SVG 里对应的就是 `fill` 与 `stroke` 二选一，
      另一个写 `none`。写错的表现是"导出图里所有线都变成黑色实心块"，而且**不报错**。
    [EN] Turn one `ft.Paint` into an SVG attribute string.
    [EN] ⚠ `ft.PaintingStyle` only has FILL / STROKE, mapping to `fill` / `stroke` (the other is
    [EN] `none`). Getting it wrong makes every line a black blob in the export, **without any error**.
    """
    if paint is None:
        return 'fill="none" stroke="none"'
    color = _color(getattr(paint, 'color', ''))
    style = getattr(paint, 'style', None)
    width = float(getattr(paint, 'stroke_width', 1.0) or 1.0)
    is_stroke = str(style).endswith('STROKE')
    if fill and not is_stroke:
        return f'fill="{color}" stroke="none"'
    extra = ''
    dash = getattr(paint, 'stroke_dash_pattern', None)
    if dash:
        extra = f' stroke-dasharray="{" ".join(str(float(x)) for x in dash)}"'
    cap = getattr(paint, 'stroke_cap', None)
    cap_s = 'round' if str(cap).endswith('ROUND') else 'butt'
    return (f'fill="none" stroke="{color}" stroke-width="{width:g}" '
            f'stroke-linecap="{cap_s}"{extra}')


def _esc(text: str) -> str:
    return (str(text or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def svg_of(shapes: list, width: int, height: int, *, background: str = '') -> str:
    """把 `build_detail_shapes()` 的结果写成一份 **SVG 文本**。

    只翻这一份形状列表里**真的会出现的**几种：`Rect` / `Line` / `Path` / `Circle` /
    `Arc` / `Text`。遇到不认识的形状**跳过并计数**（返回的串里带 `<!-- skipped:N -->`
    注释）—— 不认识的形状静默丢掉，表现是"导出图上少了几样东西"，
    那种错没人会去查，所以至少要留个记号。
    [EN] Write the result of `build_detail_shapes()` as an **SVG document**.
    [EN] Only the kinds that actually occur in that list are translated: `Rect` / `Line` / `Path` /
    [EN] `Circle` / `Arc` / `Text`. Unknown kinds are skipped and counted (a `<!-- skipped:N -->`
    [EN] comment goes into the output) -- silently dropping them shows up as "a few things missing
    [EN] from the exported map", which nobody ever investigates, so at least leave a trace.
    """
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(width)}" '
        f'height="{int(height)}" viewBox="0 0 {int(width)} {int(height)}">',
        f'<rect x="0" y="0" width="{int(width)}" height="{int(height)}" '
        f'fill="{_color(background) if background else "#ffffff"}"/>',
    ]
    skipped = 0
    for s in shapes or []:
        kind = type(s).__name__
        if kind == 'Rect':
            paint = getattr(s, 'paint', None)
            # ⚠ `border_radius` 在 flet 1.0 里是 `BorderRadius` **对象**（不是数字），
            #   直接 `float()` 会抛 `TypeError` —— 而这里一旦抛，整张图就没了
            #   （`_scene_plate_spec` 的 `except` 会把它吞成"算不出"）。
            #   所以：拿不到一个能转成数字的值就当 0（圆角只是装饰）。
            # [EN] ⚠ In flet 1.0 `border_radius` is a `BorderRadius` **object** (not a number) and
            # [EN] `float()` raises `TypeError` -- which kills the whole image (the `except` in
            # [EN] `_scene_plate_spec` swallows it as "cannot compute"). So: anything not convertible
            # [EN] to a number counts as 0 (the radius is decoration only).
            try:
                r = float(getattr(s, 'border_radius', 0) or 0)
            except (TypeError, ValueError):
                r = 0.0
            out.append(
                f'<rect x="{float(s.x):g}" y="{float(s.y):g}" '
                f'width="{float(s.width):g}" height="{float(s.height):g}"'
                + (f' rx="{r:g}"' if r else '')
                + f' {_paint_attrs(paint, fill=True)}/>')
        elif kind == 'Line':
            out.append(
                f'<line x1="{float(s.x1):g}" y1="{float(s.y1):g}" '
                f'x2="{float(s.x2):g}" y2="{float(s.y2):g}" '
                f'{_paint_attrs(getattr(s, "paint", None), fill=False)}/>')
        elif kind == 'Circle':
            out.append(
                f'<circle cx="{float(s.x):g}" cy="{float(s.y):g}" r="{float(s.radius):g}" '
                f'{_paint_attrs(getattr(s, "paint", None), fill=True)}/>')
        elif kind == 'Arc':
            out.append(
                f'<ellipse cx="{float(s.x) + float(s.width) / 2:g}" '
                f'cy="{float(s.y) + float(s.height) / 2:g}" '
                f'rx="{float(s.width) / 2:g}" ry="{float(s.height) / 2:g}" '
                f'{_paint_attrs(getattr(s, "paint", None), fill=False)}/>')
        elif kind == 'Path':
            d: list[str] = []
            for el in getattr(s, 'elements', None) or []:
                name = type(el).__name__
                if name == 'MoveTo':
                    d.append(f'M {float(el.x):g} {float(el.y):g}')
                elif name == 'LineTo':
                    d.append(f'L {float(el.x):g} {float(el.y):g}')
                elif name == 'Close':
                    d.append('Z')
                else:
                    skipped += 1
            if d:
                out.append(f'<path d="{" ".join(d)}" '
                           f'{_paint_attrs(getattr(s, "paint", None), fill=False)}/>')
        elif kind == 'Text':
            style = getattr(s, 'style', None)
            size = float(getattr(style, 'size', 12) or 12)
            color = _color(getattr(style, 'color', ''))
            weight = 'bold' if 'BOLD' in str(getattr(style, 'weight', '')) else 'normal'
            # ⚠ `fcv.Text` 的 y 是**文字左上角**（见 `minimap._text`），SVG 的 y 是**基线**。
            #   ⇒ 往下挪 `0.85 × 字号`。不挪的话每一行字都会**浮在应到的位置之上**，
            #     比例尺的刻度字会压到尺身上 —— 而那种错看着像"字号太大"。
            # [EN] ⚠ `fcv.Text`'s y is the **top-left** of the text (see `minimap._text`), while SVG's
            # [EN] y is the **baseline** => shift down by `0.85 x font size`. Without it every line
            # [EN] floats above where it belongs and the graduations land on the ruler -- which then
            # [EN] looks like "the font is too big".
            out.append(
                f'<text x="{float(s.x):g}" y="{float(s.y) + size * 0.85:g}" '
                f'font-size="{size:g}" fill="{color}" font-weight="{weight}" '
                f'font-family="Noto Serif CJK SC, Source Han Serif SC, Songti SC, serif">'
                f'{_esc(str(getattr(s, "value", "") or ""))}</text>')
        else:
            skipped += 1
    if skipped:
        out.append(f'<!-- skipped:{skipped} -->')
    out.append('</svg>')
    return '\n'.join(out)


def write_plate(path: Path, svg: str) -> bool:
    """写一张场景图（失败只记日志）。**原子写**，避免半个 SVG 留在盘上。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(svg, encoding='utf-8')
        tmp.replace(path)
        return True
    except OSError as e:
        _LOG.warning('场景地图写盘失败（导出会少一张图）：%r', e)
        return False


def load_manifest(run) -> list[dict]:
    """读清单（坏文件/版本不符 ⇒ 空表，**不抛**）。"""
    d = dir_of(run)
    if d is None:
        return []
    p = d / MANIFEST
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        _LOG.warning('场景地图清单读不出来（当作没有）：%r', e)
        return []
    if not isinstance(raw, dict) or int(raw.get('版本') or 0) != VERSION:
        _LOG.warning('场景地图清单版本不符（当作没有）')
        return []
    rows = raw.get('场景')
    return [r for r in (rows or []) if isinstance(r, dict)]


def record(run, *, day: int, index: int, place: str, when: str = '',
           svg: str = '', note: str = '', detail: str = '',
           source: str = '') -> Path | None:
    """记一场：写图 + 往清单里加一行（同一天同一场**覆盖**，不重复）。

    为什么按 `(天, 场次)` 去重而不是按地点：同一天可能**两次**回到同一个地方
    （出去一趟又回来了），那是**两个场景**，图上"人在哪"也不同，不能合并。
    [EN] Record one scene: write the image and append a row to the manifest (the same day + index
    [EN] **overwrites** instead of duplicating).
    [EN] Why key on `(day, index)` rather than on the place: the same day may **return** to the same
    [EN] place twice (went out and came back) -- those are **two scenes**, and where the people are
    [EN] differs, so they must not be merged.
    """
    d = dir_of(run)
    if d is None:
        return None
    place = str(place or '').strip() or '未命名'
    fname = plate_name(day, index, place)
    path = d / fname
    if svg and not write_plate(path, svg):
        return None
    rows = load_manifest(run)
    row = {
        '天': int(day or 0),
        '场次': int(index or 0),
        '地点': place,
        '时辰': str(when or ''),
        '图': fname,
        '描述': str(note or ''),
        '细致程度': str(detail or ''),
        '来源': str(source or ''),
    }
    rows = [r for r in rows
            if not (int(r.get('天') or 0) == row['天']
                    and int(r.get('场次') or 0) == row['场次'])]
    rows.append(row)
    rows.sort(key=lambda r: (int(r.get('天') or 0), int(r.get('场次') or 0)))
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / (MANIFEST + '.tmp')
        tmp.write_text(json.dumps({'版本': VERSION, '场景': rows},
                                  ensure_ascii=False, indent=1),
                       encoding='utf-8')
        tmp.replace(d / MANIFEST)
    except OSError as e:
        _LOG.warning('场景地图清单写盘失败：%r', e)
    return path


def plates_of_day(run, day: int) -> list[dict]:
    """某一天的场景图（按场次排好）。导出按天取，正好对上"一天一章"。"""
    return sorted([r for r in load_manifest(run) if int(r.get('天') or 0) == int(day or 0)],
                  key=lambda r: int(r.get('场次') or 0))
