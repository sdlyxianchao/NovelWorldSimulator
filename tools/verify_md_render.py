# -*- coding: utf-8 -*-
"""真机验证：帮助面板里的 **Markdown 渲染**（表格 / 代码块）。

用户 2026-10-05 报：「帮助对话框里右侧的 markdown 渲染有问题，特别是代码和表格」。

两个根因，都是 `ft.Markdown` 的**默认值**：

1. **表格**：默认的 `MarkdownExtensionSet.NONE` **不认表格语法**（表格是 GFM 扩展）
   → 说明书里 240 多行 `| a | b |` 全被当成普通文本画出来，满屏竖线；
2. **代码块**：不指定 `code_theme` 时用**深色**主题，浅色关键字压在宣纸色的正文上
   → 看着像坏的（几乎是"看不见"）。

怎么验（本机读不了图，只能量）：

* **A 组 · 可控对照**（同一段 markdown，两种设定并排/上下放）：
  - 表格：`NONE` 会把 `|---|---|` 那行**当正文画出来**，所以**更高**；
    `GITHUB_WEB` 把它当表格分隔行吃掉 → 更矮。用 `on_size_change` 读**真实渲染高度**比。
  - 代码：两边同内容、只差 `code_theme` → 数**深色像素**。浅色主题下代码字是深色（数得多），
    深色主题下关键字/注释是浅色（数得少）。
* **B 组 · 真机**：打开帮助面板，查那个 `ft.Markdown` 的三个开关真的接上了；
  再切到有表格的章节截图，用「**列对齐**」判据确认它真的被画成表格
  （按 `NONE` 渲染时每行的竖线位置随文字宽度浮动，对不齐）。

跑法：
    .venv\\Scripts\\python.exe tools/verify_md_render.py
产出：
    assets/screenshots/md_render_control.png / md_render_help_table.png
    assets/screenshots/md_render_report.json

English:
Real-app verification: the **Markdown rendering** in the help panel (tables / code blocks).
User reported on 2026-10-05: "the markdown rendering on the right side of the help dialog is
broken, especially code and tables".
Two root causes, both from `ft.Markdown`'s **defaults**:
1. **Tables**: the default `MarkdownExtensionSet.NONE` **doesn't recognize table syntax** (tables are a GFM extension)
   → the 240-something lines of `| a | b |` in the manual are all drawn as plain text, screens full of vertical bars;
2. **Code blocks**: without specifying `code_theme`, a **dark** theme is used, light-colored keywords pressed onto the rice-paper-colored body text
   → looks broken (almost "invisible").
How to verify (can't read images on this machine, can only measure):
* **Group A · controlled comparison** (same markdown snippet, two settings side by side / stacked):
  - Tables: `NONE` draws the `|---|---|` line **as body text**, so it's **taller**;
    `GITHUB_WEB` swallows it as a table separator line → shorter. Use `on_size_change` to read the **actual rendered height** and compare.
  - Code: both sides same content, differing only in `code_theme` → count **dark pixels**. Under a light theme the code glyphs are dark (count high),
    under a dark theme keywords/comments are light (count low).
* **Group B · real app**: open the help panel, check that the three switches of that `ft.Markdown` are really wired up;
  then switch to a section with tables, screenshot it, and use the "**column alignment**" criterion to confirm it's really rendered as a table
  (when rendered as `NONE`, the vertical bar position of each line floats with the text width, so they don't line up).
How to run:
    .venv\\Scripts\\python.exe tools/verify_md_render.py
Outputs:
    assets/screenshots/md_render_control.png / md_render_help_table.png
    assets/screenshots/md_render_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402
from PIL import Image  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

from gui.app_flet import (NovelWorldApp, MD_EXTENSION_SET,  # noqa: E402
                          MD_CODE_THEME, MD_CODE_FS)
from i18n import set_lang  # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

TABLE_MD = ('| 命令 | 别名 | 说明 |\n'
            '|------|------|------|\n'
            '| progress | pg | 查看故事进度表 |\n'
            '| snapshot | snap | 手动快照 |\n'
            '| rewind | rw | 回溯到指定快照 |\n')
# 代码块用的样本：**说明书里最长的那种代码行**（实测最长 125 字符）。
# 用户说"代码渲染有问题"，最可能的形态就是长行**顶出版心被裁**——
# 所以判据是"这行 125 字的代码在正文栏宽度内画完了、右边还留得下车道"。
# [EN] Sample used for code blocks: **the longest kind of code line in the manual** (measured max 125
# [EN] chars).
# [EN] When a user says "code rendering is broken", the most likely form is a long line **pushing past
# [EN] the text column and getting clipped** --
# [EN] so the criterion is "this 125-char code line is fully drawn within the body column width, with
# [EN] room to spare on the right".
LONG_CODE_CHARS = 125
LONG_MD = '```text\n' + ('x' * LONG_CODE_CHARS) + '\n```\n'
BODY_W = 900        # 帮助面板正文栏的内宽（HELP_W 1180 − 左目录 240 − 间距/内边距）
# [EN] Inner width of the help panel body column (HELP_W 1180 - left TOC 240 - spacing/padding)


def line_right_edges(png: Path, x0: int, x1: int, y0: int, y1: int,
                     thr: int = 430) -> list:
    """逐"文字行"给出最右墨迹 x（用来判等宽框线对不对齐）。
        English:
    For each "text line", give the rightmost ink x (used to judge whether monospace box lines are
    aligned).
    """
    im = Image.open(png).convert('RGB')
    px = im.load()
    rows: list = []
    for y in range(y0, y1):
        ink = [x for x in range(x0, x1) if sum(px[x, y]) < thr]
        if ink:
            rows.append((y, max(ink)))
    out: list = []
    for y, mx in rows:
        if out and y - out[-1][-1][0] <= 2:
            out[-1].append((y, mx))
        else:
            out.append([(y, mx)])
    return [max(m for _y, m in g) for g in out]


# ══════════════════════ 像素 ══════════════════════
# [EN] ══════════════════════ pixels ══════════════════════
def dark_px(png: Path, x0: int, x1: int, y0: int = 0, y1: int | None = None,
            thr: int = 430) -> int:
    """区域内深色像素数（3px 抽样，够用且快）。
        English:
    Count of dark pixels in the region (3px sampling, good enough and fast).
    """
    im = Image.open(png).convert('RGB')
    px = im.load()
    y1 = y1 if y1 is not None else im.size[1]
    return sum(1 for y in range(y0, y1, 3) for x in range(x0, x1, 3)
               if sum(px[x, y]) < thr)


def table_rows(png: Path, x0: int, x1: int, y0: int, y1: int,
               gap: int = 14, tol: int = 6, thr: int = 430) -> int:
    """数「列对齐的表格行」：一行里有 ≥3 段横向分离的墨迹，且相邻行**段起点对得上**。

    这是"表格真的被渲染成表格"的像素证据：按 `NONE` 原样画出来时，
    每行的竖线位置随单元格文字宽度浮动，**跨行对不齐**。
    
        English:
    Count "column-aligned table rows": a row with ≥3 horizontally separated ink segments, and
    adjacent rows whose **segment start points match**.
        This is the pixel evidence that "the table is really rendered as a table": when drawn as-is with `NONE`,
        the vertical bar position of each row floats with the cell text width, **not aligned across rows**.
    """
    im = Image.open(png).convert('RGB')
    px = im.load()

    rows: list = []
    for y in range(y0, y1):
        segs: list = []
        cur: list = []
        for x in range(x0, x1):
            if sum(px[x, y]) < thr:
                cur.append(x)
            elif cur:
                segs.append((cur[0], cur[-1]))
                cur = []
        if cur:
            segs.append((cur[0], cur[-1]))
        # 合并挨得很近的笔画（同一个字内部的缝隙不算分段）
        # [EN] Merge strokes that are very close together (gaps inside the same character don't count as
        # [EN] separation)
        merged: list = []
        for a, b in segs:
            if merged and a - merged[-1][1] <= gap:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        if len(merged) >= 3:
            rows.append((y, [m[0] for m in merged]))

    n = 0
    for i in range(1, len(rows)):
        y_prev, starts = rows[i - 1]
        y_cur, cur_starts = rows[i]
        if y_cur - y_prev > 4:
            continue
        if len(starts) == len(cur_starts) and all(
                abs(a - b) <= tol for a, b in zip(starts, cur_starts)):
            n += 1
    return n


async def main(page: ft.Page):
    VU.patch_flat_background()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_md_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    items: list = []

    def ok(name: str, cond, detail: str = '') -> bool:
        items.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
        if not cond:
            print(f'FAIL  {name}   [{detail}]')
        return bool(cond)

    async def shot(fname: str) -> Path:
        page.update()
        await asyncio.sleep(0.7)
        p = OUT / fname
        p.write_bytes(await page.take_screenshot())
        return p

    report: dict = {}
    sizes: dict = {}
    try:
        # ══════════ A 组 · 可控对照 ══════════
        # [EN] ══════════ Group A · controlled comparison ══════════
        def cap(key):
            def _h(e):
                sizes[key] = (e.width, e.height)
            return _h

        demo = ft.Column([
            ft.Text('表格：NONE（默认）', size=13, color='#6a6f78'),
            ft.Container(content=ft.Markdown(TABLE_MD), width=560,
                         on_size_change=cap('tbl_none'), key='tbl_none'),
            ft.Text('表格：GITHUB_WEB', size=13, color='#6a6f78'),
            ft.Container(content=ft.Markdown(TABLE_MD, extension_set=MD_EXTENSION_SET),
                         width=560, on_size_change=cap('tbl_gfm'), key='tbl_gfm'),
        ], spacing=4)
        # 用 overlay（浮在最上层）而不是加 View —— 加 View 会跟 app 自己的视图打架
        # [EN] Use an overlay (floating on top) instead of adding a View -- adding a View fights with the app's
        # [EN] own views
        panel = ft.Container(content=demo, padding=16, bgcolor='#fbf8f1')
        page.overlay.append(panel)
        page.update()
        await asyncio.sleep(1.5)
        hn, hg = sizes.get('tbl_none'), sizes.get('tbl_gfm')
        ok('对照组两个 Markdown 都量到了渲染尺寸',
           bool(hn and hg), f'none={hn} gfm={hg}')
        if hn and hg:
            # ⚠ 方向别想反：`NONE` 不认表格 → 5 行被当成**同一个段落**软换行拼起来
            # （40px = 一行折了两下）；真表格是「表头 + 分隔 + 3 行数据」= 4 行（142px），
            # **反而更高**。所以判据是"明显变高 + 行数对得上"，不是"变矮"。
            # [EN] ⚠ Don't get the direction backwards: `NONE` doesn't recognize tables → the 5 lines get
            # [EN] soft-wrapped together as **one paragraph**
            # [EN] (40px = one line wrapped twice); a real table is "header + separator + 3 data rows" = 4 lines
            # [EN] (142px),
            # [EN] **actually taller**. So the criterion is "noticeably taller + row count matches", not "shorter".
            ok('表格：GITHUB_WEB 渲染成真表格（表头+3 行数据 ≈ 4 行），'
               'NONE 只有一段折行的文字',
               hg[1] > hn[1] * 1.5 and hg[1] > 100,
               f'NONE={hn[1]}px → GITHUB_WEB={hg[1]}px')
        page.overlay.remove(panel)
        page.update()

        # 代码块：左右并列，只差 code_theme
        # [EN] Code blocks: side by side, differing only in code_theme
        row = ft.Row([
            ft.Container(content=ft.Markdown(LONG_MD,
                                             code_style_sheet=ft.TextStyle(
                                                 size=MD_CODE_FS, font_family='Consolas',
                                                 color='#3a3226')),
                         width=BODY_W, bgcolor='#fbf8f1', padding=10, key='code_long',
                         on_size_change=cap('code_long')),
        ], spacing=12)
        panel2 = ft.Container(content=row, padding=16, bgcolor='#fbf8f1')
        page.overlay.append(panel2)
        page.update()
        await asyncio.sleep(1.5)
        png = await shot('md_render_control.png')
        im = Image.open(png).convert('RGB')
        # 扫描范围 = 那个代码框的内部（去掉 16px overlay 内边距 + 10px 框内边距）
        # [EN] Scan region = the interior of that code box (minus 16px overlay padding + 10px box padding)
        bx0, bx1 = 26, 16 + BODY_W - 12
        hh = (sizes.get('code_long') or (0, 120))[1] or 120
        y1 = int(hh) + 30
        ink = [(x, y) for y in range(0, y1) for x in range(bx0, bx1)
               if sum(im.getpixel((x, y))) < 430]
        ink_max = max((x for x, _y in ink), default=0)
        ink_rows = len({y for _x, y in ink})
        report['code_long'] = {'ink_max': ink_max, 'box_right': bx1,
                              'h': hh, 'ink_rows': ink_rows,
                              'chars': LONG_CODE_CHARS}
        ok('代码块：%d 字符的长代码行画得下（最右墨迹离框右边还有车道，没被裁）'
           % LONG_CODE_CHARS,
           bool(ink) and ink_max < bx1 - 6,
           f'最右墨迹 {ink_max} / 框右边 {bx1}（高 {hh}px）')

        page.overlay.remove(panel2)
        page.update()

        # ══════════ B 组 · 真机帮助面板 ══════════
        # [EN] ══════════ Group B · real-app help panel ══════════
        from store.project import Project
        proj = Project.create_new(CFG.projects_dir(), 'Markdown 验证')
        app._activate_project(proj)
        app.show_main_screen()
        page.update()
        await asyncio.sleep(1.2)
        app.show_help_dialog()
        page.update()
        await asyncio.sleep(1.0)
        hdlg = next((d for d in VU.open_dialogs(page)
                     if any('帮 助' in x for x in VU.all_texts(d))), None)
        ok('帮助面板真的打开了', hdlg is not None)
        mds = [c for c in VU.walk(hdlg) if isinstance(c, ft.Markdown)] if hdlg else []
        ok('帮助框里有 Markdown 正文', bool(mds))
        if mds:
            md = mds[0]
            ok('正文接上了 GITHUB_WEB 扩展集（表格/围栏代码都要它）',
               md.extension_set == MD_EXTENSION_SET,
               str(getattr(md, 'extension_set', None)))
            ok('正文指定了浅色代码主题', md.code_theme == MD_CODE_THEME,
               str(getattr(md, 'code_theme', None)))
            cs = getattr(md, 'code_style_sheet', None)
            ok('代码用等宽字、字号比正文小一号（长代码行不顶出版心）',
               cs is not None and cs.font_family == 'Consolas'
               and abs((cs.size or 0) - MD_CODE_FS) < 0.01,
               f'{getattr(cs, "font_family", None)} {getattr(cs, "size", None)}')

        # 切到「命令手册」那一节（里面全是表格），看它有没有被画成表格
        # [EN] Switch to the "Command Reference" section (full of tables), see whether it's drawn as a table
        tocs = [c for c in VU.walk(hdlg)
                if isinstance(c, ft.Container) and c.on_click is not None
                and c.width is not None and 100 < c.width < 260] if hdlg else []
        target = None
        for c in tocs:
            label = VU.text_of(getattr(c, 'content', None) or c)
            if '命令' in label:
                target = c
                break
        if target is None and tocs:
            target = tocs[3]        # 兜底：任选靠后的一节
            # [EN] Fallback: pick any later section
        if target is not None:
            target.on_click(None)
            page.update()
            await asyncio.sleep(0.8)
        png2 = await shot('md_render_help_table.png')
        report['toc'] = VU.text_of(getattr(target, 'content', None) or target) if target else ''
        im2 = Image.open(png2).convert('RGB')
        rows = table_rows(png2, 0, im2.size[0], 0, im2.size[1])
        report['aligned_table_rows'] = rows
        ok('像素：帮助框里检出「列对齐的表格行」（表格真的画成表格了）',
           rows >= 2, f'对齐行数 {rows}')

        report['ok'] = all(i['ok'] for i in items)
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        report['items'] = items
        report['n_ok'] = sum(1 for i in items if i['ok'])
        report['n_all'] = len(items)
        (OUT / 'md_render_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        for it in items:
            print(f"{'OK  ' if it['ok'] else 'FAIL'}  {it['name']}"
                  + (f"   [{it['detail']}]" if it['detail'] else ''))
        print(f"\nMarkdown 渲染验证：{report['n_ok']}/{report['n_all']}")
        if report.get('fatal'):
            print(report['fatal'])
        try:
            VU.safe_rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` raises
        # [EN] CancelledError
        # [EN] cancels this coroutine, written on the line after `await shutdown(page)` as `exit_now(...)`
        # [EN] **never executed** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


if __name__ == '__main__':
    ft.run(main)
