# -*- coding: utf-8 -*-
"""真机验证：「LLM 用量」对话框的**栏宽 / 最大化 / 第 4 栏横向滚动**。

用户 2026-10-11 的原话（这一支要守住的就是它）：
    「LLM用量窗口调整下各个列的大小 第1 2 3 列适当收窄 第4列放大
      尽量保证显示所有信息 如果不行 第4列加横向滚动条 整体LLM窗口默认最大化」

★★ 这一支最值得留档的一件事：**改之前的"四栏不同宽"是假的**。
   `_pane()` 同时给了 `width=` 与 `expand=True`，而 Flet 里 `expand` 会把控件
   包进 `Expanded`（"强制撑满"约束）⇒ **`width` 被忽略，四栏等宽 ~442px**。
   所以"第 4 栏放大"在改之前**根本做不到**，而这件事在屏幕上看得见、
   在源码里看不见 —— 只有量像素才知道。
   （量法见 `developers/probe_usage_widths.py`：给四栏边框涂四种标记色，
     逐栏取该色的 x 范围。）

判据分组
--------
A 组（宽窗口 = 默认最大化）
  A1 四栏宽度**实测** == 源码 `PANE_W`（1/2/3 栏），第 4 栏 = 剩余全部
  A2 ★ 四栏**不全等**（反例正是"四栏都 442px"），且第 4 栏最宽、≥ 第 1 栏的 3 倍
  A3 ★ 对话框**默认最大化**：宽 ≈ 窗口宽 − 2×`DLG_MARGIN`，高同理
  A4 ★ 明细表**一次全显示**（表宽 ≤ 第 4 栏内容宽）—— 这就是"尽量保证显示所有信息"
  A5 第 4 栏接了横向滚动容器（抓手 `_usage_hscroll`），`scroll` 非 None
B 组（窄窗口 1060×720：把窗口改小再开）
  B1 对话框跟着窗口缩小（依旧 ≈ 窗口 − 2×边距）
  B2 ★ 第 4 栏**真的溢出了** —— 用滚动事件里的 `max_scroll_extent > 0` 判，
     不是"量表的可见宽度"。★ 这条是这一支最贵的一课：**截图只拍得到可见区**，
     被裁在栏边界上的表量出来恰好等于栏宽，于是"明明溢出"会被判成"没溢出"。
  B3 ★★ 编程横向滚动后 `pixels` 真的到了 120（滚动真能用，不是摆设）
  B4 ★★ 溢出时**自绘的横条可见**，且宽/位置按真实滚动量算
     （宽 ∝ 视口²/(视口+溢出)、左移 ∝ 滚动比例）
  B4b ★★ 那根条**真的画在屏幕上**：把它涂成标记色，量到像素，
     且位置落在第 4 栏内、明细表下方
  ⚠ 为什么**不查框架那根条**：实测两次（本支 B4 与
    `developers/probe_table_scroll.py`）—— `ADAPTIVE`→`HIDDEN` 前后截图
    **零差异**，框架根本不画常驻的横向条。所以"看得见"这件事只能靠自绘那条证。

跑法：.venv\\Scripts\\python.exe tools/verify_usage_layout.py
产出：assets/screenshots/usage_layout_*.png + usage_layout_report.json

English:
Real-device verification: the **column widths / maximization / column 4's horizontal scrolling** of
the "LLM usage" dialog.
User's exact words on 2026-10-11 (this is what this branch must guard):
    "Adjust the size of each column in the LLM usage window: narrow columns 1 2 3 a bit, widen
     column 4, try to show all the information, and if that doesn't work add a horizontal scrollbar to
     column 4; make the whole LLM window maximized by default."
★★ The most valuable thing to record here: **the "four differently wide columns" before the change was
fake**.
   `_pane()` passed both `width=` and `expand=True`, and in Flet `expand` wraps the control in an
   `Expanded` ("forced to fill" constraints) ⇒ **`width` is ignored and all four are equal ~442px**.
   So "widen column 4" was **impossible** before the change, and that fact is visible on screen but
   invisible in the source -- only measuring pixels reveals it.
   (Method in `developers/probe_usage_widths.py`: paint the four borders with four marker colors and
   take each color's x range.)
Criteria groups
--------
Group A (wide window = maximized by default)
  A1 The **measured** widths of the four columns == the source `PANE_W` (columns 1/2/3); column 4 =
     all the remainder
  A2 ★ The four are **not all equal** (the reverse case is "all four at 442px"), and column 4 is the
     widest, ≥ 3× column 1
  A3 ★ The dialog is **maximized by default**: width ≈ window width − 2×`DLG_MARGIN`, same for height
  A4 ★ The detail table **shows all at once** (table width ≤ column 4's content width) -- this is
     "show as much information as possible"
  A5 Column 4 has a horizontal scroll container wired up (handle `_usage_hscroll`) with a non-None
     `scroll`
Group B (narrow window 980×700: shrink the window and reopen)
  B1 The dialog shrinks with the window (still ≈ window − 2×margin)
  B2 ★ This time the table **really doesn't fit** (table width > column 4's width) -- the premise of
     the "if it doesn't work" branch
  B3 ★★ After a programmatic horizontal scroll, the **table's left edge really moves left** (scrolling
     works, it's not decorative)
  B4 ★★ Difference method: screenshots before/after switching `scroll` from `ADAPTIVE` to `HIDDEN`
     **differ**, and the difference lands **within the table's x range, below the table's bottom edge**
     ⇒ the horizontal scrollbar **is really drawn**
     (this is the evidence for "visible": checking only `scroll != None` proves it's wired up, not that
      anything is on screen)
How to run: .venv\\Scripts\\python.exe tools/verify_usage_layout.py
Output: assets/screenshots/usage_layout_*.png + usage_layout_report.json
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                        # noqa: E402
from PIL import Image, ImageChops                        # noqa: E402
import verify_ui_common as VU                            # noqa: E402
from util.flet_shutdown import shutdown, exit_now        # noqa: E402
from config import CFG                                   # noqa: E402

CFG.set('MOCK_LLM', 'true')
VU.redirect_env_writes()

from gui.app_flet import NovelWorldApp                   # noqa: E402
import gui.usage_dialog as UD                            # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}

#: 四栏的标记色（红 / 绿 / 蓝 / 品红）—— 只涂边框色，不动几何。
# [EN] : marker colors for the four columns (red / green / blue / magenta) -- border color only, no
# [EN] geometry change.
PANE_MARKS = {1: '#ff0000', 2: '#00ff00', 3: '#0000ff', 4: '#ff00ff'}
TABLE_MARK = '#ffff00'

#: 夹具（与 `verify_usage_filters` 同一套口径：名字中性，不把用户的书名带进截图）。
# [EN] : fixture (same convention as `verify_usage_filters`: neutral names, don't bring the user's book
# [EN] titles into screenshots).
SEED = [
    ('甲项目', 'model-a', 'crew_novelist', '小说作家', 12000, 3400, 0.20, 0),
    ('甲项目', 'model-b', 'crew_screen', '剧作者', 8000, 2200, 0.03, 0),
    ('甲项目', 'model-b', 'book_scan', '', 400, 120, 0.004, 0),
    ('乙项目', 'model-a', 'crew_review', '复盘', 5000, 1200, 0.02, 0),
]
#: 「窄窗口」的尺寸（B 组的前提）。
#: ⚠ 取 1060 而不是 980：`app_flet` 里 `w.min_width = 1024`，窗口再小会被**夹回 1024** ——
#:   夹回去本身没问题，但"我设了 980 却量到 1024"会让判据看起来像坏了。
#:   1060 下第 4 栏约 510px，而明细表实测 613px ⇒ **确实放不下**，
#:   正好落在用户说的"如果不行"那个分支上。
# [EN] : "Narrow window" size (the premise of group B).
# [EN] ⚠ 1060 rather than 980: `app_flet` has `w.min_width = 1024`, so anything smaller is **clamped
# [EN] back to 1024** -- the clamp itself is fine, but "I set 980 and measured 1024" makes the
# [EN] criterion look broken. At 1060 column 4 is ~510px while the detail table measures 613px ⇒ it
# [EN] **really doesn't fit**, landing exactly on the user's "if it doesn't work" branch.
NARROW_W, NARROW_H = 1060, 720


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'\n        {str(detail)[:220]}' if (detail and not cond) else ''))
    return bool(cond)


def client_size(page) -> tuple:
    """**客户区**尺寸 —— 对话框该按它算，不是 `page.window.*`。

    ★★ 实测（`developers/probe_window_metrics.py`，本机最大化）：
      `page.window.height = 1168` 而 `page.height = 1129`（= 截图像素高），
      差 39px 是标题栏/边框；宽度同理差 16px。
      第一版 A3 拿 `page.window.width` 当基准 ⇒ 改完"按客户区算"之后
      A3 会**假红**（1896 vs 期望 1912）—— 那是判据量错了基准，不是产品错了。

        English:
    The **client area** size -- the dialog should be computed from this, not from `page.window.*`.
        ★★ Measured (`developers/probe_window_metrics.py`, maximized on this machine):
        `page.window.height = 1168` while `page.height = 1129` (= the screenshot pixel height); the 39px
        difference is the title bar/border, and the width differs likewise by 16px.
        The first version's A3 used `page.window.width` as the baseline ⇒ after switching to
        "compute from the client area", A3 would **falsely go red** (1896 vs an expected 1912) -- that's
        the criterion measuring the wrong baseline, not the product being wrong.
    """
    return (page.width or page.window.width or 0,
            page.height or page.window.height or 0)


def hex_rgb(s: str) -> tuple:
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def color_xrange(im: Image.Image, rgb: tuple, y0: int, y1: int, tol: int = 40) -> dict:
    """整张图里该颜色的 x 范围（逐栏量边框用）。
        English:
    The x range of that color across the whole image (for measuring each column's border).
    """
    px = im.load()
    w, _h = im.size
    xs = []
    for y in range(y0, y1, 2):
        for x in range(w):
            r, g, b = px[x, y][:3]
            if abs(r - rgb[0]) < tol and abs(g - rgb[1]) < tol and abs(b - rgb[2]) < tol:
                xs.append(x)
    if not xs:
        return {}
    return {'x0': min(xs), 'x1': max(xs), 'w': max(xs) - min(xs) + 1}


def color_bbox(im: Image.Image, rgb: tuple, tol: int = 40) -> dict:
    """该颜色的外接框（找表的位置用）。
        English:
    Bounding box of that color (used to locate the table).
    """
    px = im.load()
    w, h = im.size
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y][:3]
            if abs(r - rgb[0]) < tol and abs(g - rgb[1]) < tol and abs(b - rgb[2]) < tol:
                xs.append(x)
                ys.append(y)
    if not xs:
        return {}
    return {'x0': min(xs), 'x1': max(xs), 'y0': min(ys), 'y1': max(ys),
            'w': max(xs) - min(xs) + 1, 'h': max(ys) - min(ys) + 1}


def open_dlg(page):
    """当前树里那个开着的 `AlertDialog`（取最后一个 = 最新压上去的）。
        English:
    The open `AlertDialog` currently in the tree (take the last = most recently pushed).
    """
    dlg = None
    for d in VU.open_dialogs(page):
        if isinstance(d, ft.AlertDialog):
            dlg = d
    return dlg


def pane_of(dlg, n: int):
    for c in VU.walk(dlg):
        if getattr(c, '_usage_pane', None) == n:
            return c
    return None


def hstrip_of(dlg):
    """真正横向滚动的那个控件（明细表在它里面）。
        English:
    The control that actually scrolls horizontally (the detail table is inside it).
    """
    for c in VU.walk(dlg):
        if getattr(c, '_usage_hscroll', False):
            return c
    return None


def hbar_of(dlg):
    """自己画的那根横向条（容器）。
        English:
    The horizontal bar we draw ourselves (its container).
    """
    for c in VU.walk(dlg):
        if getattr(c, '_usage_hbar', False):
            return c
    return None


def watch_scroll(scroller) -> dict:
    """给滚动控件挂 `on_scroll` 记录器 → 返回一个会被就地写入的 dict。

    ★★ 为什么必须靠滚动事件，而不是"量标记色多宽"：
      截图只拍得到**可见区** —— 640px 的内容放在 380px 视口里，量出来也是 380，
      和"被压窄到 380"在像素上**完全一样**。
      第一版就是这么量错的：B2 写"表宽 403 > 第 4 栏 418 才算放不下"，
      于是**明明溢出、却因为被裁在视口边上而量不出溢出**，判据假红。
      真正的判据是 `max_scroll_extent > 0`（"确实有滚不出去的内容"）——
      它是唯一分得开"裁"和"压"的量。
    ⚠ `on_scroll` 只在**有滚动发生时**才触发，所以调用方必须主动 `scroll_to` 一次
      （见 B 组：先 `scroll_to(offset=1)` 让事件带上 `max_scroll_extent`，
      再 `scroll_to(offset=120)` 看 `pixels` 是否真的到 120）。

        English:
    Attach an `on_scroll` recorder to a scrollable control -> returns a dict written in place.
        ★★ Why rely on scroll events rather than "how wide the marker color measures":
        a screenshot only captures the **visible area** -- 640px of content in a 380px viewport also
        measures 380, pixel-identical to "squeezed down to 380".
        The first version measured exactly that wrong way: B2 said "table width 403 > column 4's 418
        means it doesn't fit", so **genuine overflow failed to register because it was clipped at the
        viewport edge** -- a false red. The real criterion is `max_scroll_extent > 0` ("there really is
        content that can't be scrolled to") -- the only quantity that separates "clipped" from
        "squeezed".
        ⚠ `on_scroll` only fires **when a scroll happens**, so the caller must trigger one itself (see
        group B: first `scroll_to(offset=1)` so the event carries `max_scroll_extent`, then
        `scroll_to(offset=120)` to see whether `pixels` really reaches 120).
    """
    seen: dict = {}
    original = getattr(scroller, 'on_scroll', None)

    def _h(e) -> None:
        try:
            seen['pixels'] = float(getattr(e, 'pixels', 0) or 0)
            seen['max'] = float(getattr(e, 'max_scroll_extent', 0) or 0)
            seen['viewport'] = float(getattr(e, 'viewport_dimension', 0) or 0)
        except (TypeError, ValueError):
            pass
        # ★★ **必须把原来的处理器转发下去**（不能自己接了就算）：
        #   `_h_view` 里那根自绘横条就是靠这个回调重画的 —— 判据把回调抢走，
        #   条就永远不动，然后判据自己报"条没动"。这是"判据替被测对象做事"的
        #   反面：**判据替被测对象**断了它的输入。
        # [EN] ★★ **The original handler must be forwarded** (don't just take over):
        # [EN] the self-drawn horizontal bar in `_h_view` is redrawn by exactly this callback -- if the
        # [EN] criterion steals it, the bar never moves and then the criterion reports "the bar didn't
        # [EN] move". That's the flip side of "the criterion doing the object's job": **the criterion
        # [EN] cuts off the object's input**.
        if callable(original):
            original(e)

    if hasattr(scroller, 'on_scroll'):
        scroller.on_scroll = _h
    return seen


def detail_table(dlg):
    """第 4 栏里那张**明细表**（8 列、在横向滚动容器里）。

    ⚠⚠ 不能拿"第 4 栏里第一个 `DataTable`"：第 4 栏在选中之后有**两张**表 ——
      上面的「调用次数/输入 Token/…」汇总表（2 列）和下面的明细表（8 列）。
      按"第一个"抓会把汇总表当成明细表量，量出来的宽度跟"放不放得下"毫无关系
      （2026-10-11 第一版就是这么量的，A4/B2 两条判据全都量错了对象）。
      出口只有一个：**明细表在 `_usage_hscroll` 那个滚动容器里**，
      按抓手认它，不按顺序认。
    
        English:
    The **detail table** in column 4 (8 columns, inside the horizontal scroll container).
        ⚠⚠ Do not take "the first `DataTable` in column 4": after a selection column 4 has **two**
        tables -- the "calls / input tokens / ..." summary above (2 columns) and the detail table below
        (8 columns). Grabbing "the first" measures the summary and yields a width with no relation to
        "does it fit" (the first version on 2026-10-11 did exactly that; both A4 and B2 measured the
        wrong object). There is only one exit: **the detail table is inside the `_usage_hscroll` scroll
        container** -- identify it by that handle, not by order.
    """
    strip = hstrip_of(dlg)
    if strip is not None:
        for c in VU.walk(strip):
            if isinstance(c, ft.DataTable):
                return c
    return None


def click_text(dlg, text: str) -> bool:
    """点树里"可点、且子树里写着 `text`"的容器（左栏行 / 卡片都是这个形状）。
        English:
    Click the container that is "clickable and has `text` in its subtree" (left column rows / cards
    are all this shape).
    """
    for c in VU.walk(dlg):
        if getattr(c, 'on_click', None) is None:
            continue
        if not isinstance(getattr(c, 'content', None), ft.Column):
            continue
        if any(str(x) == text for x in VU.all_texts(c)):
            print(f'DBG 点到 {text}：控件={type(c).__name__} '
                  f'tag={getattr(c, "_usage_pane", None)} '
                  f'文本={[str(x)[:14] for x in VU.all_texts(c)][:4]}', flush=True)
            c.on_click(None)
            return True
    return False


async def paint_and_shot(page, dlg) -> tuple:
    """把四栏边框 + 明细表边框涂上标记色 → 截图 → 还原颜色。返回 (Image, 还原函数)。
        English:
    Paint the four column borders + the detail table's border with marker colors → screenshot →
    restore the colors. Returns (Image, restore function).
    """
    saved: list = []
    for n, col in PANE_MARKS.items():
        p = pane_of(dlg, n)
        if p is None:
            continue
        _s = ft.BorderSide(1, col)
        saved.append((p, 'border', p.border,
                      ft.Border(top=_s, bottom=_s, left=_s, right=_s)))
    table = detail_table(dlg)
    if table is not None:
        _s2 = ft.BorderSide(1, TABLE_MARK)
        saved.append((table, 'border', table.border,
                      ft.Border(top=_s2, bottom=_s2, left=_s2, right=_s2)))
    for obj, attr, _old, new in saved:
        setattr(obj, attr, new)
    page.update()
    await asyncio.sleep(1.0)
    png = await page.take_screenshot()
    im = Image.open(io.BytesIO(png)).convert('RGB')

    def restore() -> None:
        # ⚠ **同步函数**（不是 `async def`）：里面没有 await，写成协程再 `await`
        #   会得到 `TypeError: object NoneType can't be used in 'await' expression`
        #   —— 判据脚本自己崩掉，而这跟"产品坏了"在日志里长得一样。
        # [EN] ⚠ A **synchronous function** (not `async def`): there's no await inside, and making it a
        # [EN] coroutine then awaiting it yields `TypeError: object NoneType can't be used in 'await'
        # [EN] expression` -- the verify script crashes itself, which looks identical to "the product is
        # [EN] broken" in the logs.
        for obj, attr, old, _new in saved:
            setattr(obj, attr, old)
        page.update()
    return im, restore


async def measure(page, dlg, *, suffix: str) -> dict:
    """量四栏宽 + 明细表宽（涂色法）。
        English:
    Measure the four column widths + the detail table's width (marker-color method).
    """
    im, restore = await paint_and_shot(page, dlg)
    im.save(OUT / f'usage_layout{suffix}.png')
    W, H = im.size
    y0, y1 = int(H * 0.15), int(H * 0.98)
    out = {'screen': [W, H], 'panes': {}}
    for n, col in PANE_MARKS.items():
        r = color_xrange(im, hex_rgb(col), y0, y1)
        if r:
            out['panes'][n] = r
    tb = color_bbox(im, hex_rgb(TABLE_MARK))
    if tb:
        out['table'] = tb
    # 诊断：表到底有几列、几行、在不在横向滚动容器里。
    # ⚠ 这几项是**排查"表为什么这么窄"的抓手**（2026-10-11：窄窗口下表被压到
    #   恰好等于栏宽，于是"放不下"这条判据量不出溢出 —— 需要知道它当时是什么状态）。
    # [EN] Diagnostics: how many columns/rows the table has, and whether it's inside the horizontal
    # [EN] scroll container.
    # [EN] ⚠ These are the **handles for investigating "why is the table this narrow"** (2026-10-11: in
    # [EN] the narrow window the table got squeezed to exactly the column width, so the "doesn't fit"
    # [EN] criterion couldn't measure overflow -- we need to know what state it was in).
    tbls = [c for c in VU.walk(pane_of(dlg, 4)) if isinstance(c, ft.DataTable)]
    t0 = detail_table(dlg)
    if t0 is not None:
        out['table_info'] = {'n_tables_in_col4': len(tbls),
                             'cols': len(getattr(t0, 'columns', []) or []),
                             'rows': len(getattr(t0, 'rows', []) or []),
                             'is_first': bool(tbls) and tbls[0] is t0}
    strip = hstrip_of(dlg)
    out['strip'] = {'found': strip is not None,
                    'scroll': str(getattr(strip, 'scroll', None)) if strip else None,
                    'n_children': len(getattr(strip, 'controls', []) or []) if strip else 0}
    restore()
    await asyncio.sleep(0.3)
    return out


async def main(page: ft.Page) -> None:
    try:
        import llm.usage as U
        # ★ 2026-10-17 修：这一行原来接返回值赋给 `tmp`，而返回值是**换之前的老值**
        #   （用户 `.env` 的项目目录）⇒ `tmp` 指向用户真实目录（本支后面没用到它，
        #   所以只差一步就"删到用户项目上"）。⇒ 直接把返回值丢掉。
        # [EN] ★ Fixed 2026-10-17: this used to bind the return value to `tmp`, but the return value is
        # [EN] the **old value** (the user's `.env` project directory) => `tmp` pointed at the real
        # [EN] directory (unused later in this script, so one step away from "deleting the user's
        # [EN] projects"). => Drop the return value.
        VU.isolate_projects_dir(OUT / '_proj' / '栏宽验证')
        db = OUT / '_layout_usage.db'
        if db.exists():
            db.unlink()
        U.db_path = lambda: db
        now = time.time()
        for proj, mdl, pur, ag, ti, to, c, days in SEED:
            U.record(model=mdl, purpose=pur, in_tok=ti, out_tok=to, cost=c,
                     module='NovelWorldSimulator', project=proj, run='第1次模拟',
                     agent=ag, ts=now - days * 86400, path=db)

        page.enable_screenshots = True
        app = NovelWorldApp()
        app.main(page)
        page.update()
        await asyncio.sleep(1.8)

        def win_size() -> tuple:
            """客户区尺寸（判据的基准；见 `client_size` 的说明）。
                English:
            Client-area size (the criterion's baseline; see the note at `client_size`).
            """
            return client_size(page)

        # ══════════════════ A 组：宽窗口（默认最大化）══════════════════
        # [EN] ══════════════════ Group A: wide window (maximized by default) ══════════════════
        w0, h0 = win_size()
        REPORT['window_wide'] = [w0, h0]
        app.show_usage_dialog()
        await asyncio.sleep(1.6)
        dlg = open_dlg(page)
        if not ok('A0 用量对话框打开了（宽窗口）', dlg is not None):
            await shutdown(page, code=2)
            return
        # 点进"某个划分 → 某个 Agent"，让第 4 栏显示那张 8 列明细表
        # [EN] Click into "some division -> some Agent" so column 4 shows the eight-column table
        clicked = [t for t in ('model-a', '小说作家') if click_text(dlg, t)
                   and (page.update() or True)]
        await asyncio.sleep(1.2)
        REPORT['clicked'] = clicked
        ok('A0b 已点进划分与 Agent（第 4 栏因此显示 8 列明细表）',
           len(clicked) == 2, clicked)

        a = await measure(page, dlg, suffix='_wide')
        REPORT['wide'] = a
        pw = {n: a['panes'].get(n, {}).get('w', 0) for n in (1, 2, 3, 4)}
        ok('A1 三栏宽度实测 == 源码 PANE_W（第 4 栏撑满剩余）',
           all(abs(pw[n] - UD.PANE_W[n]) <= 2 for n in (1, 2, 3)) and pw[4] > 0,
           f'实测 {pw} · 源码 {UD.PANE_W}')
        ok('A2 ★ 四栏**不全等**、第 4 栏最宽且 ≥ 第 1 栏的 3 倍'
           '（反例正是改之前"四栏都 ~442px"）',
           len(set(pw.values())) > 1 and pw[4] == max(pw.values())
           and pw[4] >= pw[1] * 3,
           f'{pw}')
        box = getattr(dlg, 'content', None)
        dw, dh = getattr(box, 'width', None), getattr(box, 'height', None)
        ok('A3 ★ 对话框默认最大化（宽 ≈ 窗口宽 − 2×DLG_MARGIN，高同理）',
           dw is not None and abs(dw - (w0 - UD.DLG_MARGIN * 2)) <= 4
           and abs(dh - (h0 - UD.DLG_MARGIN * 2)) <= 4,
           f'对话框 {dw}×{dh} · 窗口 {w0}×{h0} · 期望 '
           f'{int(w0) - UD.DLG_MARGIN * 2}×{int(h0) - UD.DLG_MARGIN * 2}')
        tw = a.get('table', {}).get('w', 0)
        ok('A4 ★ 明细表**一次全显示**（表宽 ≤ 第 4 栏宽）—— "尽量保证显示所有信息"',
           tw > 0 and tw <= pw[4],
           f'表 {tw}px vs 第 4 栏 {pw[4]}px')
        strip = hstrip_of(dlg)
        ok('A5 第 4 栏接了横向滚动容器（抓手 `_usage_hscroll`，且 scroll 非 None）',
           strip is not None and getattr(strip, 'scroll', None) is not None,
           f'strip={strip is not None}')
        # A6 ★ 宽窗口放得下 ⇒ **不画**那根自绘横条（跟系统滚动条一致：
        #   没得滚就不该有条）。这是"放得下"那半，B4 是"放不下"那半。
        # [EN] A6 ★ In a wide window it fits ⇒ the self-drawn bar is **not drawn** (consistent with
        # [EN] system scrollbars: no scrollable extent, no bar). This is the "it fits" half; B4 is the
        # [EN] "it doesn't fit" half.
        thumb_a = hbar_of(dlg)
        ok('A6 ★ 宽窗口下**不画**横条（放得下就不该有条）',
           thumb_a is not None and not getattr(thumb_a, 'visible', True),
           f'thumb={thumb_a is not None} visible={getattr(thumb_a, "visible", None)}')

        try:
            page.pop_dialog()
        except Exception:                                    # noqa: BLE001
            pass
        page.update()
        await asyncio.sleep(0.6)

        # ══════════════════ B 组：窄窗口（放不下 → 该出横向滚动条）══════════════════
        # [EN] ══════════════════ Group B: narrow window (doesn't fit -> horizontal scrollbar)
        # [EN] ══════════════════
        # ⚠ **必须分两步 update**（`developers/probe_window_resize.py` 量出来的）：
        #   "退出最大化"与"设新尺寸"写在**同一个** `page.update()` 里时，
        #   框架会先把窗口还原成启动时那对兜底尺寸（1440×900），
        #   我设的 width 被那一步盖掉 —— 判据 B 组第一版就是这么量到 1440 的。
        #   分两次 update，每次都真的生效（探针里 1060×720 一次就对）。
        # [EN] ⚠ **Two separate updates are required** (measured in
        # [EN] `developers/probe_window_resize.py`): when "leave maximized" and "set the new size" go
        # [EN] into **the same** `page.update()`, the framework first restores the window to the startup
        # [EN] fallback size (1440×900), overwriting the width I set -- that's how the first version of
        # [EN] group B measured 1440. Split into two updates and each one really takes effect (the probe
        # [EN] got 1060×720 on the first try).
        page.window.maximized = False
        page.update()
        await asyncio.sleep(1.3)
        page.window.min_width = 900          # 默认 1024 会把 1060 之外的值夹回去
        # [EN] Default 1024 will clamp values outside 1060 back
        page.window.min_height = 600
        page.window.width = NARROW_W
        page.window.height = NARROW_H
        page.update()
        await asyncio.sleep(1.3)
        # 再确认一遍（有的实现要"改两次"才认）
        # [EN] Confirm once more (some implementations need "set twice" to take it)
        page.window.width = NARROW_W
        page.window.height = NARROW_H
        page.update()
        await asyncio.sleep(1.0)
        w1, h1 = win_size()
        REPORT['window_narrow'] = [w1, h1]
        ok('B0 窗口真的变小了（否则下面几条量的是同一个宽窗口）',
           abs(w1 - NARROW_W) <= 60, f'{w1}×{h1}（想要 {NARROW_W}×{NARROW_H}，客户区）')
        app.show_usage_dialog()
        await asyncio.sleep(1.6)
        dlg2 = open_dlg(page)
        if not ok('B0b 对话框在窄窗口下也打开了', dlg2 is not None):
            await shutdown(page, code=2)
            return
        clicked2 = [t for t in ('model-a', '小说作家') if click_text(dlg2, t)]
        await asyncio.sleep(1.2)
        b = await measure(page, dlg2, suffix='_narrow')
        REPORT['narrow'] = b
        pw2 = {n: b['panes'].get(n, {}).get('w', 0) for n in (1, 2, 3, 4)}
        box2 = getattr(dlg2, 'content', None)
        dw2 = getattr(box2, 'width', None)
        ok('B1 对话框跟着窗口缩小（依旧 ≈ 窗口 − 2×边距）',
           dw2 is not None and abs(dw2 - (w1 - UD.DLG_MARGIN * 2)) <= 4,
           f'对话框 {dw2} · 窗口 {w1}')
        # ⚠⚠ **这一条被删掉了，别再加回来**（2026-10-11）：
        #   原来写的是「表宽 > 第 4 栏宽 ⇒ 放不下」。它**永远不成立** ——
        #   截图只拍得到**可见区**，表被裁在栏边界上时量出来恰好等于栏宽，
        #   于是"明明溢出了"会被判成"没溢出"（假红）。
        #   溢出的正确判据是**滚动事件里的 `max_scroll_extent`**，见下面的 B2。
        # [EN] ⚠⚠ **This check was deleted; do not add it back** (2026-10-11):
        # [EN] it used to read "table width > column 4's width ⇒ it doesn't fit". That is **never
        # [EN] true** -- a screenshot only captures the **visible area**, so a table clipped at the
        # [EN] column boundary measures exactly the column width, and "genuinely overflowing" gets
        # [EN] judged as "not overflowing" (a false red). The correct overflow criterion is
        # [EN] **`max_scroll_extent` from a scroll event**, see B2 below.
        REPORT['narrow']['clicked'] = clicked2
        # ★★ B1b：**还没滚过任何一下**时，那根条就该已经出现（`_prime_hbars` 的作用）。
        #   没有它，用户打开对话框是"明明装不下、却看不到条"，非要先滚一下条才冒出来
        #   —— 而"没有条"恰恰会让人以为"不用滚"。
        #   这一条必须放在 B2/B3（那两条会主动滚动）**之前**，否则它证不了"开局就有"。
        # [EN] ★★ B1b: **before any scroll at all**, the bar should already be there (the effect of
        # [EN] `_prime_hbars`). Without it, the user opens the dialog and "it clearly doesn't fit, yet
        # [EN] there's no bar", and it only appears after they scroll once -- but "no bar" is exactly
        # [EN] what makes people think "no scrolling needed".
        # [EN] This must come **before** B2/B3 (which scroll deliberately), otherwise it proves nothing
        # [EN] about "present from the start".
        thumb_early = hbar_of(dlg2)
        ok('B1b ★★ 一次都还没滚过时，横条**就已经在**（`_prime_hbars` 主动量过一次）'
           '且可见',
           thumb_early is not None and bool(getattr(thumb_early, 'visible', False)),
           f'thumb={thumb_early is not None} '
           f'visible={getattr(thumb_early, "visible", None)}'
           f' w={getattr(thumb_early, "width", None)}'
           f' · PRIME_LOG={UD.PRIME_LOG[-4:]}')

        # ── B3/B4：真的滚一下，并用**滚动事件**证"溢出 + 能滚 + 条画出来了" ──
        # [EN] -- B3/B4: actually scroll, and use **scroll events** to prove "overflow + it scrolls +
        # [EN] the bar is drawn" --
        #
        # ★★ 判据要用 `max_scroll_extent` / `pixels`，**不是"量标记色多宽"**。
        #   截图只拍得到**可见区**：640px 的内容放在 380px 视口里量出来也是 380，
        #   与"被压窄到 380"在像素上完全一样 —— 第一版 B2 就是拿"可见宽"当溢出的，
        #   于是**明明溢出了却判成"放不下这条不成立"**（假红）。
        #   `max_scroll_extent > 0` 才是"确实有滚不出去的内容"。
        # [EN] ★★ The criterion must use `max_scroll_extent` / `pixels`, **not "how wide the marker
        # [EN] color measures"**. A screenshot only captures the **visible area**: 640px of content in a
        # [EN] 380px viewport also measures 380, pixel-identical to "squeezed to 380" -- the first
        # [EN] version's B2 used "visible width" as the overflow signal, so **genuine overflow was
        # [EN] judged as "this isn't the doesn't-fit case"** (a false red). `max_scroll_extent > 0` is
        # [EN] what means "there really is content that can't be scrolled to".
        strip2 = hstrip_of(dlg2)
        table2 = detail_table(dlg2)
        thumb2 = hbar_of(dlg2)
        if strip2 is None or table2 is None or thumb2 is None:
            ok('B3 ★★ 编程横向滚动后 `pixels` 真的到了 120（滚动真能用）', False,
               f'strip={strip2 is not None} table={table2 is not None} '
               f'thumb={thumb2 is not None}')
        else:
            seen = watch_scroll(strip2)
            page.update()
            await asyncio.sleep(0.4)
            # ① 先滚 1px：让事件带上 `max_scroll_extent`（on_scroll 只在真滚动时才触发）
            # [EN] (1) scroll 1px first so the event carries `max_scroll_extent` (on_scroll only fires
            # [EN] on a real scroll)
            try:
                await strip2.scroll_to(offset=1, duration=0)
            except Exception as e:                           # noqa: BLE001
                REPORT['scroll_error'] = repr(e)
            await asyncio.sleep(1.2)
            REPORT['b3_probe'] = dict(seen)
            mx = float(seen.get('max', 0) or 0)
            vp = float(seen.get('viewport', 0) or 0)
            ok('B2 ★ 第 4 栏**真的溢出了**（`max_scroll_extent > 0`，'
               '= 有滚不出去的内容）—— "如果不行"那个分支的前提',
               mx > 2, f'max_scroll_extent={mx} viewport={vp} 实测={seen}')

            # ② 再滚到 120：`pixels` 必须跟着到 120（这才是"滚得动"）
            # [EN] (2) then scroll to 120: `pixels` must follow to 120 (that's "it scrolls")
            try:
                await strip2.scroll_to(offset=120, duration=200)
            except Exception:                                # noqa: BLE001
                pass
            await asyncio.sleep(1.4)
            REPORT['b3'] = dict(seen)
            got_px = float(seen.get('pixels', 0) or 0)
            ok('B3 ★★ 编程横向滚动后 `pixels` 真的到了 120（滚动真能用，不是摆设）',
               got_px >= 100, f'pixels={got_px}（想要 ≈120）· {seen}')

            # ③ 自绘那根横条：溢出时**可见**，且宽度/位置是**按真实滚动量**算的
            # [EN] (3) The self-drawn bar: **visible** when overflowing, and its width/position are
            # [EN] computed from the real scroll metrics
            REPORT['b4'] = {'visible': bool(getattr(thumb2, 'visible', False)),
                            'w': getattr(thumb2, 'width', None),
                            'left': getattr(thumb2, 'left', None),
                            'viewport': vp, 'max': mx}
            want_w = max(40.0, vp * vp / (vp + mx)) if (vp and mx > 1) else 0
            want_left = ((vp - want_w) * (min(120.0, mx) / mx)
                         if (mx > 1 and want_w) else 0)
            ok('B4 ★★ 溢出时**自绘横条可见**，且宽度/位置按真实滚动量算出来'
               '（宽 ∝ 视口²/(视口+溢出)，左移 ∝ 滚动比例）',
               bool(getattr(thumb2, 'visible', False))
               and abs(float(getattr(thumb2, 'width', 0) or 0) - want_w) <= 3
               and abs(float(getattr(thumb2, 'left', 0) or 0) - want_left) <= 3,
               f'实测 w={getattr(thumb2, "width", None)} left={getattr(thumb2, "left", None)}'
               f' · 期望 w={want_w:.1f} left={want_left:.1f} · vp={vp} mx={mx}')

            # ④ 那根条**真的画在屏幕上**（像素证据）—— 把它涂成标记色再量
            # [EN] (4) That bar is **really drawn on screen** (pixel evidence) -- paint it with a
            # [EN] marker color and measure
            old_bg = thumb2.bgcolor
            _s3 = ft.BorderSide(0, '#000000')
            old_th = (thumb2.height, thumb2.border)
            thumb2.bgcolor = TABLE_MARK
            thumb2.height = 6
            thumb2.border = ft.Border(top=_s3, bottom=_s3, left=_s3, right=_s3)
            page.update()
            await asyncio.sleep(1.0)
            im_bar = Image.open(io.BytesIO(await page.take_screenshot())).convert('RGB')
            bb = color_bbox(im_bar, hex_rgb(TABLE_MARK))
            REPORT['b4_pixels'] = bb
            # 条必须落在**第 4 栏的 x 区间**里、且在明细表底边之下
            # [EN] The bar must fall within **column 4's x range** and below the detail table's bottom
            # [EN] edge
            tb = b.get('table', {})
            inside = bool(bb) and bb['x0'] >= pw2[4] - 30 and pw2[4] > 0 \
                and bb['x1'] <= 1900
            ok('B4b ★★ 那根横条**真的画出来了**（标记色量到像素），'
               '位置在第 4 栏内、明细表下方',
               bool(bb) and inside,
               f'标记色框={bb} · 第4栏 x={b["panes"].get("4", {}).get("x0")}..'
               f'{b["panes"].get("4", {}).get("x1")}')
            thumb2.bgcolor = old_bg
            thumb2.height, thumb2.border = old_th
            page.update()


        # ── 收尾：把窗口还原成最大化，别影响后面的判据 ──
        # [EN] -- Cleanup: restore the window to maximized so later criteria aren't affected --
        try:
            page.window.maximized = True
            page.update()
        except Exception:                                    # noqa: BLE001
            pass
    except BaseException:                                    # noqa: BLE001
        import traceback
        REPORT['fatal'] = traceback.format_exc()
        ok('未抛异常（整轮跑完）', False, REPORT['fatal'][-220:])
    finally:
        passed = sum(1 for c in REPORT['checks'] if c['ok'])
        total = len(REPORT['checks'])
        REPORT.update({'passed': passed, 'total': total,
                       'ok': passed == total and not REPORT.get('fatal')})
        (OUT / 'usage_layout_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n用量窗口栏宽/最大化/横向滚动验证：{passed}/{total}')
        await shutdown(page, code=0 if REPORT['ok'] else 2)


if __name__ == '__main__':
    try:
        ft.run(main, assets_dir=str(APP_DIR / 'assets'))
    except Exception:                                        # noqa: BLE001
        exit_now(2)
