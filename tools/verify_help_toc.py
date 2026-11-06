# -*- coding: utf-8 -*-
"""验证：Markdown 有序列表里**两位数的标号不会折行**（"每行多一个点"那个 bug）。

用户原话（2026-10-06）：
「帮助文件目录**从 10 开始后面每行多一个点**。你看下怎么回事。」

真因（`developers/probe_md_listnum.py` 扫出来的）：`MarkdownStyleSheet.list_indent`
是**留给标号的那条道**，原来只按 `1.`（两字符）留 16px；到了 `10.`（三字符）放不下，
**标号自己被折到第二行** —— 屏幕上看就是"多出来一个孤零零的点"，而且那一项还高出一截。
实测行距：`list_indent=16 → [26×9, 46, 46, 46, 46]`（10..14 那几项被折），
`24/30/34/40 → 全是 26`。所以 `MD_LIST_INDENT` 定成 28。

判据是**像素**的，而且判的是**行距一致性**（不是行数）：
折行时那一项会高出一截，但**行数不变**（折出来的点跟在标号下面），
所以"数行数"这条会瞎绿 —— 只有量行距才抓得住。

跑法：`.venv\\Scripts\\python.exe tools/verify_help_toc.py`
产出：assets/screenshots/help_toc_*.png + help_toc_report.json

English:
Verify: in a Markdown ordered list, **two-digit numbers do not wrap** (the "one extra dot per
line" bug).
User's exact words (2026-10-06):
"In the help file TOC, **starting from 10 there's an extra dot on every line**. Take a look at
what's going on."
Root cause (scanned out by `developers/probe_md_listnum.py`): `MarkdownStyleSheet.list_indent`
is **the lane reserved for the number**; originally it only reserved 16px for `1.` (two
characters); by `10.` (three characters) it no longer fits,
**the number itself wraps to the second line** -- on screen this looks like "an extra lone dot",
and that item is also taller by a bit.
Measured line spacing: `list_indent=16 -> [26x9, 46, 46, 46, 46]` (items 10..14 are wrapped),
`24/30/34/40 -> all 26`. So `MD_LIST_INDENT` is set to 28.
The criterion is in **pixels**, and it checks **line-spacing consistency** (not line count):
when wrapped that item becomes taller by a bit, but **the line count does not change** (the
wrapped dot sits under the number),
so "count the lines" goes falsely green -- only measuring line spacing catches it.
How to run: `.venv\\Scripts\\python.exe tools/verify_help_toc.py`
Output: assets/screenshots/help_toc_*.png + help_toc_report.json
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('UI_LANG', 'zh')

from gui.app_flet import (NovelWorldApp, md_style_sheet, mk_md,  # noqa: E402
                          MD_LIST_INDENT, read_manual)
from i18n import set_lang, t  # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
ITEMS: list = []


def ok(name: str, cond, detail: str = '') -> bool:
    ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


def line_gaps(png: Path, x0: int = 0, x1: int = None) -> list:
    """图里每个文字行的 y，返回相邻行的**行距**列表。

    ⚠ 只数"墨迹"，横线/边框不算：要求这一行至少有 2 个墨迹像素。
    
        English:
    For each text line's y in the image, return the list of **line spacings** between adjacent
    lines.
        ⚠ Count only "ink"; horizontal lines/borders do not count: require this line to have at least 2 ink pixels.
    """
    from PIL import Image
    im = Image.open(png).convert('RGB')
    px = im.load()
    W, H = im.size
    x1 = min(x1 or W, W)
    ys = []
    for y in range(H):
        n = sum(1 for x in range(x0, x1, 2) if sum(px[x, y]) < 620)
        if n >= 2:
            ys.append(y)
    grp: list = []
    for y in ys:
        if grp and y - grp[-1][-1] <= 2:
            grp[-1].append(y)
        else:
            grp.append([y])
    tops = [g[0] for g in grp]
    return [b - a for a, b in zip(tops, tops[1:])]


def uniform(gaps: list, tol: int = 4) -> bool:
    """行距是不是「一样高」。

    ⚠ **不能要求严格相等**：行的 y 是按"第一个墨迹像素"取的，
    首字有没有上伸部（`1` 比 `产` 高一点）会让同一档差 1~2px，
    实测正常值是 25/26/27 混着来，所以给 ±4 的余量。
    这个余量足够宽（折行是 46 vs 26，差 20），也足够紧（不会放过折行）。
    
        English:
    Whether the line spacings are "all the same height".
        ⚠ **Cannot require strict equality**: a line's y is taken from the "first ink pixel",
        whether the first character has an ascender (`1` is slightly taller than `产`) causes a 1~2px difference within the same tier,
        measured normal values come mixed as 25/26/27, so allow a ±4 margin.
        This margin is wide enough (wrapping is 46 vs 26, a difference of 20), and tight enough (it won't let wrapping slip through).
    """
    return bool(gaps) and (max(gaps) - min(gaps)) <= tol


async def main(page: ft.Page):
    report: dict = {}
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.window.width = 900
    page.window.height = 1040      # 要放得下 32 行（32×26≈830）
    # [EN] Must fit 32 lines (32×26≈830)
    page.update()
    await asyncio.sleep(2.0)

    async def render(name: str, md: str, width: int = 760):
        page.controls.clear()
        page.add(ft.Container(
            content=mk_md(md, selectable=False),
            width=width, padding=14, bgcolor='#fbf9f2'))
        page.update()
        await asyncio.sleep(0.6)
        p = OUT / name
        p.write_bytes(await page.take_screenshot())
        return p

    try:
        # ══════════ A. 说明书里那份**真的**「目录」══════════
        # [EN] ══════════ A. The **actual** "table of contents" in the manual ══════════
        _intro, sections = read_manual(APP_DIR / '使用说明.md')
        toc_md = next((b for ti, b in sections if ti.strip() == '目录'), '')
        n_src = len(re.findall(r'(?m)^\s*\d+\.\s', toc_md))
        report['toc_items_in_source'] = n_src
        ok('A：说明书里确实有一份「目录」有序列表（≥14 项）', n_src >= 14, n_src)

        png = await render('help_toc_1_real.png', toc_md)
        gaps = line_gaps(png)
        report['real_gaps'] = gaps
        report['list_indent'] = MD_LIST_INDENT
        ok('A：★ 真·目录渲染出来**每行一样高**（折行的那几项会高出一截）',
           uniform(gaps), f'行距 {gaps}')
        ok('A：★ 行距列表里**没有 46 那种"高一倍"的行**（折行的铁证）',
           all(g <= 30 for g in gaps), f'行距 {gaps}')
        ok('A：目录 14 项一行一项（没被折成两行）',
           len(gaps) + 1 >= n_src, f'{len(gaps) + 1} 行 / 源里 {n_src} 项')

        # ══════════ B. 放大版：32 项（说明书以后变长也不能再犯）══════════
        # [EN] ══════════ B. Scaled-up version: 32 items (even if the manual grows longer later, this must not
        # [EN] happen again) ══════════
        big = '\n'.join(f'{i}. [第 {i} 节](#第-{i}-节)' for i in range(1, 33))
        png2 = await render('help_toc_2_big.png', big)
        gaps2 = line_gaps(png2)
        report['big_gaps'] = gaps2
        ok('B：★ 32 项的有序列表（含 10/20/30 这些两位标号）行距也一致',
           uniform(gaps2), f'行距 {sorted(set(gaps2))} × {len(gaps2)}')
        # ⚠ 行数要够：列表比视口长的话**下面几行根本没渲染**，
        #   数出来的行距偏少会让这条判据变成"看不见就当过了"（第一版就是这么瞎绿的）。
        # [EN] ⚠ Enough rows required: if the list is longer than the viewport, **the rows below simply are not
        # [EN] rendered**,
        # [EN] counting too few row spacings will turn this criterion into "if you can't see it, it passes"
        # [EN] (the first version went green exactly this blindly).
        ok('B：32 项全渲染出来了（窗口够高，没被截断）', len(gaps2) == 31, len(gaps2))

        # ══════════ C. 这条道到底留多宽（把"为什么是 28"钉住）══════════
        # [EN] ══════════ C. Exactly how wide this lane should be (nail down "why 28") ══════════
        report['min_indent_needed'] = 24
        ok('C：★ `MD_LIST_INDENT` ≥ 实测下限 24（16 会折行，实测见文件头）',
           MD_LIST_INDENT >= 24, MD_LIST_INDENT)
        ok('C：`md_style_sheet()` 真的把 MD_LIST_INDENT 用上了（不是摆设）',
           md_style_sheet().list_indent == MD_LIST_INDENT,
           str(md_style_sheet().list_indent))

        n_ok = sum(1 for i in ITEMS if i['ok'])
        report['items'] = ITEMS
        report['ok'] = n_ok == len(ITEMS)
        print(f'\n帮助目录标号验证：{n_ok}/{len(ITEMS)}')
    except Exception:                                          # noqa: BLE001
        report['items'] = ITEMS
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
        print(report['fatal'])
    finally:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'help_toc_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will raise
        # [EN] CancelledError
        # [EN] cancel this coroutine, written on the line after `await shutdown(page)` as `exit_now(...)`
        await shutdown(page, code=0 if report.get('ok') else 1)


if __name__ == '__main__':
    ft.run(main)
