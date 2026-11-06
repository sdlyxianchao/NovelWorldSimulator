# -*- coding: utf-8 -*-
"""验证：**帮助面板左栏（目录）的滚动条**（2026-10-09）。

用户原话：

    「帮助窗口**左边的下拉滚动条又没了**」

查到底是**两个错叠在一起**（都在这条判据里钉住）：

  ① **面板被静默裁掉一截**：`HELP_PANE_H` 只减了选项卡条，没算框架还拿走的
     标题行 / 选项卡条真实高度 / 底部按钮 —— 实测面板画在 y=380，
     可见部分只到 y=833（只有 453px），而代码按 552px 排版，
     于是目录**最后一条半被裁掉**，屏幕上没有任何提示。
  ② **"要不要出条"的估算用的是没被裁的高度**：`toc_avail = 540`、
     内容只有 493 → 判"放得下" → 不出条；可真实可用只有 441 → 超出 52px。

判据分层（每层都要能红，见 `developers/mutate_help_scrollbar.py`）：

  A **源码级**：版面高度必须减掉那个保留量（= 估算与实际同源）
  B **真机 · 不能被裁**：面板容器的**可见底边** ≥ 它的排版高度
    —— "内容看不见了却没人说"是这条要拦的东西
  C **真机 · 该出条就出条**：左栏内容超出容器时，那条 4px 的条
    **真的画在屏幕上**（像素取证，不是查控件属性）
  D **真机 · 不该出条就不出**：内容放得下时**不能**画条
    （画一条滚不动的条比不画更糟）

用法：.venv\\Scripts\\python.exe tools/verify_help_scrollbar.py
产出：assets/screenshots/help_scrollbar_report.json / help_bar_toc_*.png

English:
Verification: **the scrollbar of the help panel's left column (table of contents)**
(2026-10-09).
The user's exact words:
    "The **dropdown scrollbar on the left side of the help window is gone again**"
Traced it down to **two bugs stacked together** (both pinned by this criterion):
  ① **The panel is silently clipped by a chunk**: `HELP_PANE_H` only subtracted the tab bar, not accounting for what the frame also takes ——
     the title row / the tab bar's real height / the bottom buttons —— measured that the panel is drawn at y=380,
     the visible part only reaches y=833 (only 453px), while the code lays out for 552px,
     so the table of contents' **last one and a half entries are clipped**, with no indication on screen.
  ② **The "should a bar appear" estimate uses the unclipped height**: `toc_avail = 540`,
     content is only 493 → judged "it fits" → no bar; but the real available space is only 441 → over by 52px.
Criterion layering (each layer must be able to turn red, see
`developers/mutate_help_scrollbar.py`):
  A **source level**: the layout height must subtract that reserved amount (= estimate and actual share the same source)
  B **real machine · must not be clipped**: the panel container's **visible bottom edge** ≥ its layout height
    —— "the content is invisible yet nobody says anything" is what this layer must catch
  C **real machine · show the bar when it should**: when the left column's content exceeds the container, that 4px bar
    **is really drawn on screen** (pixel evidence, not querying control properties)
  D **real machine · don't show the bar when it shouldn't**: when the content fits, the bar **must not** be drawn
    (drawing a bar that can't scroll is worse than not drawing one)
Usage: .venv\\Scripts\\python.exe tools/verify_help_scrollbar.py
Output: assets/screenshots/help_scrollbar_report.json / help_bar_toc_*.png
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown                        # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')
VU.redirect_env_writes()

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from gui import app_flet as G                                  # noqa: E402
from gui.app_flet import (NovelWorldApp, HELP_H, HELP_TAB_H,   # noqa: E402
                          HELP_PANE_H, HELP_PANE_RESERVED_H,
                          HELP_TOC_LANE, SET_H, toc_row_h)

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  A. 源码级：估算与版面**同源**（这是这个 bug 的根）
# [EN] A. Source-level: estimation and layout must **share the same source** (this is the root of this
# [EN] bug)
# ══════════════════════════════════════════════════════════════════
def test_source() -> bool:
    ok_ = True
    import inspect
    src = inspect.getsource(G.NovelWorldApp._help_reader_pane)
    REPORT['pane_h'] = G.HELP_PANE_H
    REPORT['reserved'] = G.HELP_PANE_RESERVED_H

    ok_ &= ok('A1 ★★★ 版面高度**减掉了框架要拿走的那些**'
              '（只减搜索行不够 —— 不减就会被静默裁掉一截）',
              'HELP_PANE_RESERVED_H' in src, '')
    ok_ &= ok('A2 ★★★ 保留量是**正的、且够大**'
              '（实测 99；取小了照样裁）',
              isinstance(HELP_PANE_RESERVED_H, int)
              and HELP_PANE_RESERVED_H >= 60, str(HELP_PANE_RESERVED_H))
    # 估算必须跟着同一个 `pane_h` 走（不能一边减、一边不减）
    # [EN] Estimation must follow the same `pane_h` (cannot subtract on one side while not subtracting on
    # [EN] the other)
    ok_ &= ok('A2b ★★ 估算用的可用高 = **同一个 `pane_h`** 减内边距'
              '（一边减一边不减，估算就与实际差一截 —— 正是这个 bug）',
              'toc_avail = pane_h - 12' in src.replace('HELP_TOC_PAD', '12')
              or 'toc_avail = pane_h' in src, '')

    # 真实可用高度 vs 目录内容高度：**当前示例说明书**该判"超出"
    # [EN] Real available height vs TOC content height: **the current example help text** should be judged
    # [EN] "overflow"
    n = None
    try:
        _, secs = G.read_manual(APP_DIR / '使用说明.md')
        n = 1 + len(secs)
    except Exception:                                          # noqa: BLE001
        pass
    pane_h = HELP_PANE_H - SET_H - 10 - HELP_PANE_RESERVED_H
    avail = pane_h - 12
    content = (n or 0) * toc_row_h()
    REPORT['geom'] = {'n_items': n, 'row_h': toc_row_h(), 'avail': avail,
                      'content': content}
    ok_ &= ok('A3 ★★★ 保留量必须让**目录内容高度**与可用高度可比 —— '
              '17 条 × 29px = 493 应当**超出**可用（否则这条判据测不到东西）',
              avail < content,
              f'可用 {avail} vs 内容 {content:.0f}（条数 {n}）')
    return ok_


# ══════════════════════════════════════════════════════════════════
#  像素助手（按色相判 —— 界面可能半透明，按原色比会量到 0）
# [EN] Pixel helper (judge by hue — the UI may be semi-transparent, comparing by original color would
# [EN] measure 0)
# ══════════════════════════════════════════════════════════════════
def find_green_box(png: bytes, x_from: int = 0, x_to: int | None = None):
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert('RGB')
    W, H = im.size
    px = im.load()
    x2 = W if x_to is None else min(W, x_to)
    xs, ys = [], []
    for y in range(H):
        for x in range(max(0, x_from), x2):
            r, g, b = px[x, y]
            if g > r + 40 and g > b + 40 and g > 90:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def magenta_extent(png: bytes, x_from: int = 380, x_to: int = 700):
    """所有品红像素的 (y_min, y_max)。用并集，避免被行高亮/文字打断。
        English:
    The (y_min, y_max) of all magenta pixels. Use the union, to avoid being interrupted by line
    highlights/text.
    """
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert('RGB')
    W, H = im.size
    px = im.load()
    ys = []
    for y in range(H):
        for x in range(max(0, x_from), min(W, x_to)):
            r, g, b = px[x, y]
            if r > g + 60 and b > g + 60:
                ys.append(y)
                break
    return (min(ys), max(ys)) if ys else None


def vertical_runs(png: bytes, rgb, x: int, tol: int = 8,
                  y_from: int = 0, y_to: int | None = None):
    """某一列上 rgb 色的纵向连续区段（>3px）。
        English:
    The vertically continuous segment (>3px) of rgb color on a given column.
    """
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert('RGB')
    W, H = im.size
    px = im.load()
    y2 = H if y_to is None else min(H, y_to)
    runs, cur = [], None
    for y in range(max(0, y_from), y2):
        c = px[x, y]
        good = all(abs(a - b) <= tol for a, b in zip(c, rgb))
        if good and cur is None:
            cur = y
        elif not good and cur is not None:
            if y - cur > 3:
                runs.append((cur, y - 1))
            cur = None
    if cur is not None:
        runs.append((cur, y2 - 1))
    return runs


# ══════════════════════════════════════════════════════════════════
#  B/C/D. 真机
# [EN] B/C/D. Real device
# ══════════════════════════════════════════════════════════════════
async def test_ui(page: ft.Page) -> bool:
    ok_ = True
    page.enable_screenshots = True
    app = NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(1.0)
    app.show_help_dialog()
    page.update()
    await asyncio.sleep(1.6)

    dlgs = VU.open_dialogs(page)
    dlg = dlgs[-1] if dlgs else None
    ok_ &= ok('B0 帮助对话框打开了', dlg is not None, '')

    stacks = [c for c in VU.walk(dlg) if isinstance(c, ft.Stack)]
    toc_stack = stacks[0] if stacks else None
    ok_ &= ok('B0b 找到左栏那条自绘滚动条（Stack）', toc_stack is not None,
              f'{len(stacks)} 个 Stack')
    if toc_stack is None:
        return ok_

    toc_lv = toc_stack.controls[0]
    thumb = toc_stack.controls[1]
    rows = list(getattr(toc_lv, 'controls', []) or [])
    REPORT['rows'] = len(rows)
    REPORT['thumb_initial'] = {'visible': bool(getattr(thumb, 'visible', False)),
                              'height': getattr(thumb, 'height', None)}

    # ── B ★★★ 面板**没有被裁**（可见底边 ≥ 排版高度）──
    #   做法：把面板容器染成品红，量它在屏幕上**真实可见**的纵向范围。
    # [EN] ── B ★★★ The panel is **not clipped** (visible bottom edge ≥ layout height) ──
    # [EN] Method: paint the panel container magenta and measure its **truly visible** vertical extent on
    # [EN] screen.
    toc_holder = None
    for c in VU.walk(dlg):
        if isinstance(c, ft.Container) and c is not toc_stack:
            inner = getattr(c, 'content', None)
            if inner is toc_stack:
                toc_holder = c
                break
    ok_ &= ok('B0c 找到左栏容器', toc_holder is not None, '')
    old_bg = getattr(toc_holder, 'bgcolor', None) if toc_holder else None
    if toc_holder is not None:
        toc_holder.bgcolor = '#ff00ff'
    page.update()
    await asyncio.sleep(0.7)
    png = await page.take_screenshot() or b''
    (OUT / 'help_bar_toc_holder.png').write_bytes(png)
    # ⚠ **量"所有品红像素的纵向并集"，不要量某一列** —— 容器里有目录行
    #   （选中的那行 `bgcolor=C['border']`）与文字，单列会被它们打断，
    #   第一版就是这么量到"高 42"这种离谱值的（面板其实好端端在那里）。
    # [EN] ⚠ **Measure the vertical union of ALL magenta pixels, do not measure a single column** —— the
    # [EN] container has TOC rows
    mag = magenta_extent(png)
    REPORT['toc_visible'] = mag
    vis = mag
    need_h = toc_holder.height if toc_holder is not None else None
    REPORT['toc_height_declared'] = need_h
    ok_ &= ok('B1 ★★★ 左栏面板在屏幕上**完整可见**（没有被框架静默裁掉）',
              vis is not None and need_h is not None
              and (vis[1] - vis[0] + 1) >= need_h - 4,
              f'可见 {vis}（高 {vis[1]-vis[0]+1 if vis else "?"}）'
              f'｜声明高 {need_h}')
    if toc_holder is not None:
        toc_holder.bgcolor = old_bg
    page.update()
    await asyncio.sleep(0.3)

    # ── C ★★★ 内容超出 ⇒ 条**真的画在屏幕上** ──
    # [EN] ── C ★★★ Content exceeds ⇒ the bar is **actually drawn on screen** ──
    avail = (toc_holder.height if toc_holder is not None else 0) - 12
    content = len(rows) * toc_row_h()
    REPORT['need_scroll'] = content > avail
    old = thumb.bgcolor
    thumb.bgcolor = '#00ff00'
    page.update()
    await asyncio.sleep(0.6)
    png2 = await page.take_screenshot() or b''
    (OUT / 'help_bar_toc_on.png').write_bytes(png2)
    box = find_green_box(png2)
    REPORT['bar_box'] = box
    ok_ &= ok('C1 ★★★ 左栏目录**超出容器**时，滚动条真的画在屏幕上'
              '（像素取证 —— 查 `thumb.visible` 是不够的：'
              '控件可见不等于画得出来）',
              (not REPORT['need_scroll']) or (
                  bool(getattr(thumb, 'visible', False)) and box is not None
                  and box[3] > box[1]),
              f'need_scroll={REPORT["need_scroll"]}｜visible='
              f'{getattr(thumb, "visible", None)}｜box={box}')
    # 条要在**右边缘的车道里**，不是压在文字上
    # [EN] The bar must be **in the lane at the right edge**, not on top of the text
    ok_ &= ok('C2 ★★ 条贴在本栏**右边缘的车道**里（不压目录文字）',
              box is None or (toc_holder is not None
                              and box[0] >= 380 + (toc_holder.width or 240) - 40),
              str(box))

    # ── D ★★★ 反过来：内容放得下时**不出条** ──
    #   ⚠⚠ **必须走产品自己的判断路径**（检索框 → `_rebuild` → `reset(...)`），
    #   不能自己调 `toc_stack.reset(False)` —— 那样测的是"这个回调能不能听话"，
    #   而不是"产品判得对不对"。实测踩过：第一版直接调 `reset`，
    #   于是"把产品改成永远画条"这个变异**谁也打不红**（反例法当场揭穿）。
    # [EN] ── D ★★★ Inverse: when content fits, **no bar** ──
    # [EN] ⚠⚠ **Must go through the product's own decision path** (search box → `_rebuild` → `reset(...)`),
    # [EN] Do not call `toc_stack.reset(False)` yourself — that tests "can this callback obey",
    # [EN] not "is the product's judgment correct". Seen in practice: the first version called `reset`
    # [EN] directly,
    # [EN] so the mutation "make the product always draw the bar" **could not be flagged red by anyone**
    # [EN] (counterexample method exposed it on the spot).
    thumb.bgcolor = old
    page.update()
    search = next((c for c in VU.walk(dlg)
                   if isinstance(c, ft.TextField)), None)
    ok_ &= ok('D0 找得到左栏上面的检索框（D 组要靠它走产品路径）',
              search is not None, '')
    if search is not None:
        # ⚠ 必须带 `e.control` —— 产品的接线是 `lambda e: _rebuild(e.control.value)`，
        #   传 `None` 会 `AttributeError` → **整段 D 组一条都不记**（判据静默失效）。
        class _Ev:                          # 别叫 `_E`：模块级别处有同名
        # [EN] ⚠ Must pass `e.control` — the product's wiring is `lambda e: _rebuild(e.control.value)`,
        # [EN] passing `None` will `AttributeError` → **not a single item in the entire D group gets recorded**
        # [EN] (the criteria silently fail).
        # [EN] Don't name it `_E`: a same-named module-level thing exists
            pass
        _ev = _Ev()
        _ev.control = search
        # 一个**必然 0 命中**的词 → 左栏只剩 0 行 → 产品自己会判"放得下"
        # [EN] A word that **necessarily has 0 hits** → the left column has only 0 rows left → the product
        # [EN] itself will judge "it fits"
        search.value = 'zzz这个词一定没有789'
        _r = search.on_change(_ev)
        if hasattr(_r, '__await__'):
            await _r
        page.update()
        await asyncio.sleep(0.7)
        REPORT['after_empty_search'] = {
            'rows': len(getattr(toc_lv, 'controls', []) or []),
            'visible': bool(getattr(thumb, 'visible', False))}
        ok_ &= ok('D1 ★★★ 检索到 0 条时，左栏**没有条目**且条**藏起来**'
                  '（产品自己判的 —— 画一条滚不动的条比不画更糟）',
                  len(getattr(toc_lv, 'controls', []) or []) == 0
                  and not bool(getattr(thumb, 'visible', False)),
                  str(REPORT['after_empty_search']))
        # 清空检索 → 17 条回来 → 条必须**自己回来**
        # [EN] Clear the search → 17 entries come back → the entries must **come back on their own**
        search.value = ''
        _r2 = search.on_change(_ev)
        if hasattr(_r2, '__await__'):
            await _r2
        page.update()
        await asyncio.sleep(0.8)
        REPORT['after_clear_search'] = {
            'rows': len(getattr(toc_lv, 'controls', []) or []),
            'visible': bool(getattr(thumb, 'visible', False))}
        # ★★ 2026-10-12 改口径（帮助"最大化"之后）：原来这里**要求条必须可见**，
        #   而那个期望是**按旧面板高（453）**写的 —— 当时 17 行 × 30 = 510 > 441，
        #   所以"该有"。面板放大到 667 之后 17 行**放得下**，正确行为是**不画条**
        #   （产品自己的原则：画一条滚不动的条比不画更糟，见 D1）。
        #   所以判据改成验**"它是按当前数字现算的"**：可见性必须等于
        #   `内容高 > 可用高`。这一条同样盖住"一次定死"（定死的实现会在
        #   内容变小之后仍然显示，或在内容变大之后仍然隐藏）。
        # [EN] ★★ 2026-10-12 changed criteria (after help became "maximized"): this used to
        # [EN] **require the bar to be visible**, an expectation written for the **old panel height
        # [EN] (453)** -- back then 17 rows x 30 = 510 > 441, so a bar was due. With the panel enlarged to
        # [EN] 667 the 17 rows **fit**, and the correct behaviour is **not to draw a bar** (the product's
        # [EN] own principle: a bar that cannot move is worse than none, see D1).
        # [EN] So the criterion now checks **that the decision is recomputed from the current numbers**:
        # [EN] visibility must equal `content height > available height`. This also covers "decided once
        # [EN] and frozen" (a frozen implementation would keep showing it after the content shrinks, or
        # [EN] keep hiding it after the content grows).
        _avail_now = max(0, int((toc_holder.height if toc_holder is not None else 0)) - 12)
        _content_now = len(getattr(toc_lv, 'controls', []) or []) * toc_row_h()
        _want_bar = _content_now > _avail_now
        ok_ &= ok('D2 ★★★ 清空检索、目录回到 17 条 → 条的可见性**按当前数字现算**'
                  '（换检索词时要能重新判断，不能一次定死）'
                  f'｜内容 {_content_now} vs 可用 {_avail_now}',
                  bool(getattr(thumb, 'visible', False)) == _want_bar
                  and len(getattr(toc_lv, 'controls', []) or []) > 0,
                  str(REPORT['after_clear_search'])
                  + f'｜内容 {_content_now} 可用 {_avail_now} 应有条 {_want_bar}')
    return ok_


def finish() -> int:
    (OUT / 'help_scrollbar_report.json').write_text(
        json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    # ★★★ 判据**自己崩了必须算红**（2026-10-09 反例法抓出来的）：
    #   第一版把异常写进 `REPORT['fatal']` 就完事，而 `bad` 只数 `checks` ——
    #   于是"脚本中途抛异常、后面的断言一条都没跑"看起来是**全绿**。
    #   那种绿比红危险得多（它会把一个假的"通过"留在报告里）。
    # [EN] ★★★ The criterion **must itself turn red when it crashes** (caught by the 2026-10-09
    # [EN] counterexample method):
    # [EN] The first version just wrote the exception into `REPORT['fatal']` and called it done, while
    # [EN] `bad` only counted `checks` ——
    # [EN] So "the script threw an exception midway and not a single later assertion ran" looked **all
    # [EN] green**.
    # [EN] That kind of green is far more dangerous than red (it leaves a fake "pass" in the report).
    bad = [c for c in REPORT['checks'] if not c['ok']]
    if REPORT.get('fatal'):
        bad = bad + [{'name': '判据自身崩了（见 fatal）', 'detail': '',
                      'ok': False}]
    n = len(REPORT['checks'])
    print(f'\n帮助左栏滚动条验证：{n - (len(bad) - (1 if REPORT.get("fatal") else 0))}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}   [{c["detail"]}]')
    print('→ 全部通过' if not bad else '→ 有失败项')
    return 0 if not bad else 1


async def entry(page: ft.Page) -> None:
    try:
        REPORT['source_ok'] = test_source()
        REPORT['ui_ok'] = await test_ui(page)
    except BaseException:                                      # noqa: BLE001
        import traceback
        REPORT['fatal'] = traceback.format_exc()[-1800:]
        print(REPORT['fatal'])
    finally:
        await shutdown(page, code=finish())


if __name__ == '__main__':
    ft.run(entry)
    sys.exit(finish())
