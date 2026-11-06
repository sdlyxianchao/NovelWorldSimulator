# -*- coding: utf-8 -*-
"""真机验证：几处关键界面的**常驻滚动条**真的画出来了。

起因（用户 2026-10-06）：
    「回答问题的地方回答区也需要滚动条，开卷的AI部分左侧和右侧也需要滚动条，
      运行窗口的输出对话的地方也需要滚动条，还有别的地方你看下我有遗漏吗，
      有就加上」

为什么必须有这条判据
====================
`_scroll_bar` 画的是一块 **4px 的 `Container`，浮在一个 `ft.Stack` 上**
（因为控件级/主题级 `thumb_visibility=True` 在这个 Flet 构建里都不生效，
见它的 docstring）。这种东西"控件树里查得到"与"屏幕上看得见"是两回事 ——
本项目在这上面栽过很多次，所以：

  · **A 组（纯逻辑，不开窗）**：条的结构（`Stack` 两个子项、thumb 恰好 4px）、
    `reset` / `sync` 的语义（`sync` 只在可见性变化时才动控件、已可见时不动它）、
    各处车道常量都不小于条宽；
  · **B 组（真机）**：逐个界面打开 → 找到条 → **把 thumb 临时染成品红**
    （标记色法，**只动颜色不动几何**）→ 截图 → 数像素：
    既要"画出来了"（≥20 个品红像素、整条 ≥24px 长），
    又要"画在了该在的地方"（**是一根 ≤8px 宽的竖条**，落在界面右半侧）。
    顺手把"内容一多 → 条自己出现"这条**接线**也验一遍（不然就是假按钮）。

跑法：
    .venv\\Scripts\\python.exe tools/verify_scrollbars.py
产出：
    assets/screenshots/scrollbars_help.png / _ingest.png / _run.png / _resume.png
    assets/screenshots/scrollbars_report.json

English:
Real-device verification: the **persistent scrollbars** on several key screens really do get
drawn.
Origin (user, 2026-10-06):
    "The answer area also needs a scrollbar, the left and right sides of the ingest AI section also need scrollbars,
      the output/chat area of the run window also needs a scrollbar, and check the other places for anything I missed,
      add them if so"
Why this assertion is required
====================
`_scroll_bar` draws a **4px `Container` floating on an `ft.Stack`**
(because control-level/theme-level `thumb_visibility=True` doesn't take effect in this Flet
build,
see its docstring). For such a thing, "findable in the control tree" and "visible on screen" are
two different matters ——
this project has tripped on this many times, so:
  · **Group A (pure logic, no window)**: the bar's structure (`Stack` with two children, thumb exactly 4px),
    the semantics of `reset` / `sync` (`sync` only touches the control when visibility changes; when already visible it doesn't touch it),
    and the lane constant everywhere is no smaller than the bar width;
  · **Group B (real device)**: open each screen one by one → find the bar → **temporarily dye the thumb magenta**
    (marker-color method, **only change color, not geometry**) → screenshot → count pixels:
    both "it got drawn" (≥20 magenta pixels, whole bar ≥24px long),
    and "it's drawn where it should be" (**it's a vertical bar ≤8px wide**, landing on the right half of the screen).
    Also verify the **wiring** "more content → bar appears on its own" (otherwise it's a fake button).
How to run:
    .venv\\Scripts\\python.exe tools/verify_scrollbars.py
Outputs:
    assets/screenshots/scrollbars_help.png / _ingest.png / _run.png / _resume.png
    assets/screenshots/scrollbars_report.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                        # noqa: E402
import verify_ui_common as VU                            # noqa: E402
from util.flet_shutdown import shutdown, exit_now        # noqa: E402

from config import CFG                                   # noqa: E402
CFG.set('MOCK_LLM', 'true')                              # 零网络、零成本、可复现
# [EN] Zero network, zero cost, reproducible
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from gui.app_flet import NovelWorldApp, chat_bubble      # noqa: E402
import gui.app_flet as G                                 # noqa: E402
from i18n import set_lang                                # noqa: E402
set_lang(_lang)

VU.redirect_env_writes()          # 全程禁写真实 `.env`（见它的 docstring）
# [EN] Never write the real `.env` throughout (see its docstring)

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'

MAGENTA = (255, 0, 255)          # 标记色：全项目没有一处用它
BAR_W = 4                        # `_scroll_bar` 画的条宽（改了这里要一起改）
# [EN] Marker color: it is not used anywhere in the whole project
# [EN] Width of the bar drawn by `_scroll_bar` (changing this requires changing it together)
report: dict = {}
checks: list = []


def ok(name: str, cond, detail='') -> bool:
    checks.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:200]})
    return bool(cond)


def bars_in(root) -> list:
    """树里所有"自绘滚动条"（`Stack([内容, 4px 的 thumb])`）。
        English:
    All "self-drawn scrollbars" in the tree (`Stack([content, 4px thumb])`).
    """
    out: list = []
    for c in VU.walk(root):
        if not isinstance(c, ft.Stack):
            continue
        kids = list(getattr(c, 'controls', None) or [])
        if len(kids) != 2:
            continue
        t = kids[1]
        if (isinstance(t, ft.Container)
                and int(getattr(t, 'width', 0) or 0) == BAR_W
                and callable(getattr(c, 'reset', None))):
            out.append(c)
    return out


def thumb_of(bar):
    return (getattr(bar, 'controls', None) or [None, None])[1]


def magenta_bbox(png: bytes) -> dict:
    """截图里的品红像素：个数 / x 范围 / y 范围。

    ⚠ 逐像素跑 Python 循环在 1920×1129 上要两三秒一张 —— 改成
    `split()` 出三条通道 + `point()` 出掩膜 + `ImageChops.multiply()` 合成，
    全部在 C 层做（`histogram()` 数个数、`getbbox()` 拿范围）。
    
        English:
    Magenta pixels in the screenshot: count / x range / y range.
        ⚠ A per-pixel Python loop on 1920×1129 takes two or three seconds per image —— switch to
        `split()` into three channels + `point()` for the mask + `ImageChops.multiply()` to combine,
        all done at the C layer (`histogram()` counts, `getbbox()` gets the range).
    """
    from PIL import ImageChops
    im = VU.image_of(png)                 # 已经是 RGB
    # [EN] Already RGB
    r, g, b = im.split()
    mask = ImageChops.multiply(
        r.point(lambda v: 255 if v > 190 else 0),
        ImageChops.multiply(g.point(lambda v: 255 if v < 90 else 0),
                            b.point(lambda v: 255 if v > 190 else 0)))
    n = mask.histogram()[255]
    bb = mask.getbbox()
    if not n or not bb:
        return {'n': 0, 'w': im.size[0], 'h': im.size[1]}
    return {'n': n, 'x0': bb[0], 'y0': bb[1], 'x1': bb[2] - 1, 'y1': bb[3] - 1,
            'w': im.size[0], 'h': im.size[1]}


async def shoot(page, name: str) -> bytes:
    page.update()
    await asyncio.sleep(0.45)
    data = await page.take_screenshot()
    (OUT / f'{name}{SUFFIX}.png').write_bytes(data)
    return data


# ══════════════════════════════════════════════════════════════════
#  A 组：纯逻辑（不开窗，构造一个没有 page 的 App 直接调 `_scroll_bar`）
# [EN] Group A: pure logic (no window opened; construct an App without page and call `_scroll_bar`
# [EN] directly)
# ══════════════════════════════════════════════════════════════════
def logic_checks() -> None:
    app = NovelWorldApp()                 # `self.page` 是 None —— `_scroll_bar` 不用它
    # [EN] `self.page` is None -- `_scroll_bar` does not use it
    body = ft.ListView(controls=[], spacing=2, expand=True)
    bar = app._scroll_bar(body, 300, lane=20)
    th = thumb_of(bar)

    ok('A1 条是一个 `Stack`，两个子项（内容 + thumb）',
       isinstance(bar, ft.Stack) and len(bar.controls) == 2
       and bar.controls[0] is body, type(bar).__name__)
    ok('A2 thumb 是一块 4px 宽的窄条（不是一整块面板）',
       isinstance(th, ft.Container) and th.width == BAR_W, th.width)
    ok('A3 一开始是藏着的（内容放得下就不该有）',
       th.visible is False, th.visible)
    ok('A4 车道比条宽（≥8 才不至于压在最右那列字上）',
       all(int(v) >= 8 for v in (
           # 模块级常量
           # [EN] Module-level constants
           __import__('gui.app_flet', fromlist=['x']).HELP_TOC_LANE,
           __import__('gui.app_flet', fromlist=['x']).HELP_BODY_LANE,
           __import__('gui.app_flet', fromlist=['x']).HELP_CHAT_LANE,
           __import__('gui.app_flet', fromlist=['x']).ING_LANE,
           __import__('gui.app_flet', fromlist=['x']).MSG_BAR_LANE,
           __import__('gui.app_flet', fromlist=['x']).SAVE_GUTTER,
       )))

    bar.reset(True)
    ok('A5 `reset(True)` → 条现身，且长度不小于 24px（太短的条抓不住）',
       th.visible is True and float(th.height) >= 24, f'{th.visible} / {th.height}')
    th.top = 50.0
    bar.sync(True)
    ok('A6 已经可见时 `sync(True)` **不动**它（否则逐行追加会让条一直抖）',
       float(th.top) == 50.0, th.top)
    bar.sync(False)
    ok('A7 `sync(False)` → 收起来（可见性变了才动）', th.visible is False, th.visible)
    bar.sync(False)
    ok('A8 重复 `sync(False)` 是幂等的', th.visible is False, th.visible)
    bar.reset(False)
    ok('A9 `reset(False)` → 明确收起（换到没内容的页面时用）',
       th.visible is False, th.visible)

    # 车道真的留出来了（不是"常量写了但没用上"）
    # [EN] The lane is really reserved (not "constant written but unused")
    lv = ft.ListView(controls=[], padding=ft.Padding(0, 0, 22, 0), expand=True)
    ok('A10 `ListView` 的车道在它自己的 padding 里（右内边距 = 车道）',
       int(getattr(lv.padding, 'right', 0) or 0) == 22, lv.padding)

    # ★★ A11：套了自绘条之后，被套控件的 `scroll` 必须被关成 HIDDEN。
    #   否则 Flet 的框架条会**再画一根**：`ScrollMode.ADAPTIVE` 在桌面端是
    #   "always shown"（官方文档），于是同一个面板上出现"一细一粗"两根 ——
    #   用户 2026-10-07 报的「有的窗口是2个滑动条 一个粗的 一个细的」就是这个。
    #   实测（`developers/probe_double_scrollbar.py` 差分法）：自绘条在 x1499..1502（4px），
    #   框架条在 x1503..1510（8px，浅灰）并排；改成 HIDDEN 后后者消失。
    # [EN] ★★ A11: after wrapping with the custom-drawn bar, the wrapped control's `scroll` must be turned
    # [EN] off to HIDDEN.
    # [EN] Otherwise Flet's framework bar will **draw another one**: `ScrollMode.ADAPTIVE` on desktop is
    # [EN] "always shown" (official docs), so the same panel ends up with two bars, "one thin and one
    # [EN] thick" --
    # [EN] This is exactly what the user reported on 2026-10-07 as "some windows have 2 scrollbars, one
    # [EN] thick, one thin".
    # [EN] Measured (`developers/probe_double_scrollbar.py` differential method): the custom bar is at
    # [EN] x1499..1502 (4px),
    # [EN] the framework bar is side by side at x1503..1510 (8px, light gray); after changing to HIDDEN the
    # [EN] latter disappears.
    lv2 = ft.ListView(controls=[], spacing=2, expand=True)
    lv2.scroll = ft.ScrollMode.ADAPTIVE          # 故意给一个"会画框架条"的模式
    # [EN] Deliberately give a mode that "will draw the framework bar"
    bar2 = app._scroll_bar(lv2, 300, lane=20)
    ok('A11 ★ 套自绘条后，被套控件的 scroll 被关成 HIDDEN（防"一粗一细"两根）',
       lv2.scroll == ft.ScrollMode.HIDDEN, lv2.scroll)
    col = ft.Column([], scroll=ft.ScrollMode.AUTO)
    app._scroll_bar(col, 300, lane=20, scroller=col)
    ok('A12 ★ `Column(scroller=…)` 那条路也一样关掉（Column 也会画框架条）',
       col.scroll == ft.ScrollMode.HIDDEN, col.scroll)
    # A13：是**就地改属性**，不是把控件换掉 —— 否则调用方手里的引用就失效了
    # （调用方后面还会 `lv.controls = …` 地往里塞内容）。
    # [EN] A13: it is **in-place attribute modification**, not replacing the control -- otherwise the
    # [EN] caller's reference becomes invalid
    # [EN] (the caller will later stuff content in via `lv.controls = ...`).
    ok('A13 关框架条是就地改属性（原控件对象仍是栈里的那个）',
       isinstance(bar2, ft.Stack) and bar2.controls[0] is lv2,
       f'controls[0] is lv2 = {getattr(bar2, "controls", [None])[0] is lv2}')


# ══════════════════════════════════════════════════════════════════
#  B 组：真机
# [EN] Group B: real machine
# ══════════════════════════════════════════════════════════════════
async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)

    tmp = Path(tempfile.mkdtemp(prefix='nws_sbar_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    report['tmp'] = str(tmp)

    async def measure(bar, label: str, note: str) -> dict:
        """标记色法：把 thumb 染成品红 → 截图 → 量它。**只动颜色不动几何**。
                English:
        Marker-color method: dye the thumb magenta → screenshot → measure it. **Only change color, not
        geometry**.
        """
        th = thumb_of(bar)
        old = th.bgcolor
        try:
            bar.reset(True)                 # 保证这一轮它真的是可见的
            # [EN] Ensure it is really visible in this round
            th.bgcolor = '#ff00ff'
            png = await shoot(page, label)
        finally:
            th.bgcolor = old
        m = magenta_bbox(png)
        report.setdefault('marks', {})[label] = {'note': note, **m}
        return m

    # ── ① 帮助 · 问个问题（回答区）──────────────────────────────
    # [EN] ── ① Help · Ask a question (answer area) ──────────────────────────────
    try:
        app.show_help_dialog(tab=1)
        page.update()
        await asyncio.sleep(0.8)
        bar = app._ui_help.get('chat_bar')
        col = app._ui_help.get('chat_col')
        dlgs = VU.open_dialogs(page)
        in_tree = bool(bars_in(dlgs[-1]) if dlgs else [])
        ok('B1 帮助窗口打开了', bool(dlgs), len(dlgs))
        ok('B2 「问个问题」的聊天列挂上了自绘条', bar is not None and in_tree,
           f'bar={bar is not None} in_tree={in_tree}')
        ok('B3 车道做在聊天列自己的 padding 里（右侧内边距 = 车道）',
           int(getattr(getattr(col, 'padding', None), 'right', 0) or 0) >= 8,
           getattr(col, 'padding', None))

        # 灌几条气泡 —— 检查"内容一多，条自己就出来"（接线，走真实的 `_push`）
        # [EN] Feed a few bubbles -- check "when content grows, the bar appears by itself" (wiring, goes
        # [EN] through the real `_push`)
        push = app._ui_help.get('push')
        ok('B4a 「问个问题」的气泡工厂接上了（`_push` 可用）', callable(push), push)
        for i in range(10):
            if callable(push):
                push('assistant', '这是第 %d 条测试回答。' % i + '正文长一点，好让它折行。' * 3)
        page.update()
        ok('B4 气泡多起来之后条自动现身（内容 → 条 这条接线是通的）',
           thumb_of(bar).visible is True, thumb_of(bar).visible)

        m = await measure(bar, 'scrollbars_help', '帮助 · 问个问题 回答区')
        ok('B5 帮助回答区的条**真的画在屏幕上**（品红像素 ≥20）',
           m.get('n', 0) >= 20, m)
        ok('B6 它是一根**窄条**，不是一整块（宽度 ≤8px）',
           m.get('n', 0) >= 20 and (m.get('x1', 0) - m.get('x0', 0)) <= 8, m)
        ok('B7 长度 ≥24px（条太短抓不住）',
           m.get('n', 0) >= 20 and (m.get('y1', 0) - m.get('y0', 0)) >= 24, m)
        ok('B8 位置在窗口**右半侧**（贴在面板右边缘）',
           m.get('n', 0) >= 20 and m.get('x0', 0) > m.get('w', 0) * 0.5, m)
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.3)
    except Exception:                                        # noqa: BLE001
        report['help_fatal'] = traceback.format_exc()
        ok('B1 帮助窗口打开了', False, '崩溃，见报告 help_fatal')

    # ── ①b 帮助 · 翻（右栏正文的条：**按"表格密集节"验，别只验"很长的节"**）──
    # [EN] ── ①b Help · Scroll (bar of the right column body: **verify with a "table-dense section", not
    # [EN] just a "very long section"**) ──
    #
    # ★★ 为什么单列这一组（2026-10-07 用户报"帮助信息这个地方还是没有滚动条"）：
    #   右栏原来按**字数**判要不要露条（阈值约 1380 字），而**表格/代码是"字少行多"**，
    #   于是这些节被系统性低估、条不出现、内容被截断：
    #     §1 产品介绍 977字/约1075px · §7 运行模式 987字/1113px · §8 快照与版本 550字/902px
    #     §11 常见问题 1002字/946px · §12 故障排除 748字/792px（容器内高只有 536px）
    #   所以判据改用 `md_height_est()`（按行类型估）。这一组钉的就是"表格节必须露条"。
    _TOC_H = G.toc_row_h()          # 与界面**同一个式子**，不另抄一份
    # [EN] ★★ Why single out this group (2026-10-07 user reported "the help info here still has no
    # [EN] scrollbar"):
    # [EN] The right column originally decided whether to show the bar by **word count** (threshold about
    # [EN] 1380 chars), while **tables/code are "few chars, many lines"**,
    # [EN] so these sections were systematically underestimated, the bar did not appear, and content was
    # [EN] truncated:
    # [EN] §1 Product introduction 977 chars / about 1075px · §7 Run modes 987 chars / 1113px · §8
    # [EN] Snapshots and versions 550 chars / 902px
    # [EN] §11 FAQ 1002 chars / 946px · §12 Troubleshooting 748 chars / 792px (container inner height is
    # [EN] only 536px)
    # [EN] So the criterion was changed to use `md_height_est()` (estimated by line type). This group pins
    # [EN] exactly "table sections must show the bar".
    # [EN] Same formula as the UI, do not copy another one
    try:
        app.show_help_dialog(tab=0)
        page.update()
        await asyncio.sleep(0.8)
        dlgs = VU.open_dialogs(page)
        hdlg = dlgs[-1] if dlgs else None
        body_bar = app._ui_help.get('body_bar')
        toc_bar = app._ui_help.get('toc_bar')
        body_col = app._ui_help.get('body_col')
        ok('C1 「翻」页的两条都挂上了（body_bar / toc_bar）',
           body_bar is not None and toc_bar is not None,
           f'body={body_bar is not None} toc={toc_bar is not None}')

        def _is_toc(c):
            if not (isinstance(c, ft.Container) and c.on_click is not None
                    and c.border_radius == 4):
                return False
            pad = getattr(c, 'padding', None)
            return (getattr(pad, 'left', None) == 6
                    and getattr(pad, 'top', None) == 4)

        tocs = [c for c in VU.walk(hdlg) if _is_toc(c)] if hdlg else []
        ok('C2 左栏目录项找得到（≥10 条）', len(tocs) >= 10, len(tocs))

        def click_title(prefix: str):
            """按标题前缀点目录项 —— 走真实 `on_click` 接线。
                        English:
            Click directory entries by title prefix —— goes through the real `on_click` wiring.
            """
            for c in tocs:
                texts = [str(x) for x in VU.all_texts(c)]
                if any(prefix in x for x in texts):
                    c.on_click(None)
                    return True
            return False

        # 表格密集但字数少的那一节 —— 修复前这里 `visible` 是 False
        # [EN] The section that is table-dense but has few chars -- before the fix `visible` here was False
        hit1 = click_title('产品介绍')
        page.update()
        await asyncio.sleep(0.7)
        ok('C3 点得到「产品介绍」（表格密集、字数少的那节）', hit1)
        ok('C4 ★ 表格密集节：右栏条**露出来了**（内容超出 536px）',
           thumb_of(body_bar).visible is True, thumb_of(body_bar).visible)

        # 很短的节 —— 不该多画条
        # [EN] A very short section -- should not draw an extra bar
        hit2 = click_title('合规说明')
        page.update()
        await asyncio.sleep(0.7)
        ok('C5 点得到「合规说明」（很短的节）', hit2)
        ok('C6 短节：右栏条**收起来**（内容放得下就不画）',
           thumb_of(body_bar).visible is False, thumb_of(body_bar).visible)

        # 像素级复核：`visible=True` 只是"控件属性说它可见"，
        # 还要证明它**真的画到了屏幕上**（这是本项目对 UI 的一贯要求）。
        # ⚠ 这里**不能**用 `measure()`：它内部会 `reset(True)` 强制可见，
        #   那就把"判据自己该不该露条"这件事绕过去了。只染颜色、不动几何与可见性。
        # [EN] Pixel-level recheck: `visible=True` only means "the control attribute says it is visible",
        # [EN] it still must be proven that it is **really drawn on screen** (this is the project's consistent
        # [EN] requirement for UI).
        # [EN] ⚠ Here `measure()` **cannot** be used: internally it does `reset(True)` to force visibility,
        # [EN] which bypasses the question of "whether the criterion itself should show the bar". Only tint the
        # [EN] color, do not touch geometry or visibility.
        hit1b = click_title('产品介绍')
        page.update()
        await asyncio.sleep(0.7)
        th = thumb_of(body_bar)
        old_bg = th.bgcolor
        old_auto = getattr(body_col, 'auto_scroll', None)
        try:
            th.bgcolor = '#ff00ff'
            # ★ 必须**真的发生一次滚动**，否则框架条不会渲染（Flutter 的 Scrollbar
            #   默认只在滚动活动中露脸）—— 那样这一条就抓不到"两根条"的回归。
            #   不能用 `scroll_to()`（它会阻塞整个 asyncio 循环，见 `mk_scroll_bar`
            #   的注释）；改用 `auto_scroll=True` 让 ListView 自己滚到底，
            #   同样产生滚动活动，且不碰事件循环。测完在 finally 里还原。
            # [EN] ★ A scroll **must actually happen**, otherwise the framework bar will not render (Flutter's
            # [EN] Scrollbar
            # [EN] by default only shows up during scroll activity) -- in that case this check cannot catch the
            # [EN] "two bars" regression.
            # [EN] `scroll_to()` cannot be used (it blocks the entire asyncio loop, see the comment in
            # [EN] `mk_scroll_bar`
            # [EN] ); instead use `auto_scroll=True` to let the ListView scroll to the bottom by itself,
            # [EN] which also produces scroll activity and does not touch the event loop. Restore in finally after
            # [EN] the test.
            if hasattr(body_col, 'auto_scroll'):
                body_col.auto_scroll = True
            page.update()
            await asyncio.sleep(0.8)
            png = await shoot(page, 'scrollbars_help_reader')
        finally:
            th.bgcolor = old_bg
            if old_auto is not None:
                body_col.auto_scroll = old_auto
                try:
                    page.update()
                except Exception:                            # noqa: BLE001
                    pass
        mk = magenta_bbox(png)
        report.setdefault('marks', {})['scrollbars_help_reader'] = {
            'note': '帮助 · 翻（表格密集节）右栏条', **mk}
        ok('C11 ★ 表格密集节的右栏条**真的画在屏幕上**（品红像素 ≥20，未强制）',
           hit1b and mk.get('n', 0) >= 20, mk)

        # ★★ C12/C13：**屏幕上只能有一根条**。
        #   这类"多画了一根"的 bug 控件属性查不出来（自绘条和框架条各归各的体系），
        #   只能数像素。**但"数竖条"要按"很长的连续竖直段"来数**：
        #   文字像素同样偏离底色，按"每列偏离计数"去点会把**每一列有文字的列**
        #   都算成条（实测：一整片文字被并成一根 74px 的"条"，判据全废）。
        #   条是连续的（高 184~553px），文字行只有 ~15px —— 用**最长连续段**区分。
        # [EN] ★★ C12/C13: **there can be only one bar on screen**.
        # [EN] This kind of "drew one extra bar" bug cannot be found from control attributes (the custom bar
        # [EN] and framework bar belong to separate systems),
        # [EN] so pixels must be counted. **But "counting vertical bars" must be done by "very long consecutive
        # [EN] vertical segments"**:
        # [EN] text pixels also deviate from the background color; counting deviations per column would mark
        # [EN] **every column that has text**
        # [EN] as a bar (measured: a whole patch of text got merged into one 74px "bar", and the criterion was
        # [EN] completely useless).
        # [EN] A bar is continuous (height 184~553px), a text line is only ~15px -- distinguish using the
        # [EN] **longest consecutive segment**.
        def bar_strips(png: bytes, x0: int, x1: int, y0: int, y1: int,
                       min_run: int = 80) -> list:
            im = VU.image_of(png)
            px = im.load()
            # 底色取整片区域的中位数（取单点容易被文字/边框带偏）
            # [EN] Take the background color as the median of the whole region (taking a single point is easily
            # [EN] skewed by text/borders)
            samp = sorted(px[x, y][:3] for x in range(x0, x1, 3)
                          for y in range(y0, y1, 7))
            bg = samp[len(samp) // 2]
            out, cur = [], None
            for x in range(x0, x1):
                best = run = 0
                for y in range(y0, y1):
                    r, g, b = px[x, y][:3]
                    if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > 90:
                        run += 1
                        best = max(best, run)
                    else:
                        run = 0
                if best >= min_run:
                    cur = [x, x] if cur is None else [cur[0], x]
                elif cur is not None:
                    out.append(tuple(cur))
                    cur = None
            if cur is not None:
                out.append(tuple(cur))
            return out

        ok('C12 右栏 `body_col.scroll` 是 HIDDEN（框架条已关）',
           getattr(app._ui_help.get('body_col'), 'scroll', None) == ft.ScrollMode.HIDDEN,
           getattr(app._ui_help.get('body_col'), 'scroll', None))
        # ⚠ `bb` 要在**本组内**取：它是分组局部变量，跨组引用会 NameError
        #   （2026-10-07 踩到：C13 直接崩，还被汇总裁成了"通过"）。
        # [EN] ⚠ `bb` must be taken **within this group**: it is a group-local variable, and referencing it
        # [EN] across groups causes NameError
        # [EN] (hit on 2026-10-07: C13 crashed directly, and the summary still aggregated it as "passed").
        cbb = VU.dialog_bbox(png)
        if cbb:
            # 三类要分开：
            #   1px 的 —— 容器**边框竖线**（也够长，会被连续段法量到），不算条；
            #   3~10px —— 真·滚动条（自绘 4px / 框架 8px）；
            #   ≥12px —— 两根**紧挨着**被合并成一条宽带（单根不可能这么宽）。
            # [EN] Three categories must be separated:
            # [EN] 1px -- container **border vertical line** (also long enough that the consecutive-segment method
            # [EN] detects it), not counted as a bar;
            # [EN] 3~10px -- real scrollbar (custom 4px / framework 8px);
            # [EN] ≥12px -- two bars **right next to each other** merged into one wide band (a single bar cannot be
            # [EN] this wide).
            st = bar_strips(png, cbb[2] - 90, cbb[2] - 2, cbb[1] + 80, cbb[3] - 30)
            report.setdefault('marks', {})['reader_strips'] = st
            bars = [s for s in st if 3 <= (s[1] - s[0] + 1) <= 10]
            wide = [s for s in st if (s[1] - s[0] + 1) >= 12]
            ok('C13 车道里的自绘条是**细条**（3~10px），且没有被合并成宽带',
               len(bars) == 1 and not wide,
               f'全部条带 {st}｜条(3~10px) {bars}｜过宽(≥12px) {wide}')
            # ⚠ **别把 C13 当成"两根条"的检测器**（试过，不可靠）：
            #   框架条只在**滚动活动发生的那几帧**渲染。这里能用的"造滚动"手段只有
            #   `auto_scroll=True`（`scroll_to()` 会阻塞事件循环，不能用）——
            #   实测把"关框架条"那行禁掉之后，本张截图的条带**一个字都没变**
            #   （C13 照旧通过），可同一状态在 `developers/probe_double_scrollbar.py`
            #   里是**能**量到那根 8px 框架条的（x1503..1510）。即它受渲染时机影响。
            #   → "两根条"的回归交给**确定性**的 A11 / A12 / C12（查 `scroll` 模式）：
            #     反例法实测那三条会红（53/56），够用。
            # [EN] ⚠ **Do not treat C13 as a "two bars" detector** (tried it, unreliable):
            # [EN] The framework bar only renders during **the frames when scroll activity happens**. The only
            # [EN] "create scroll" means usable here is
            # [EN] `auto_scroll=True` (`scroll_to()` blocks the event loop, cannot be used) --
            # [EN] measured: after disabling the line that "turns off the framework bar", the bar band in this
            # [EN] screenshot **did not change at all**
            # [EN] (C13 still passed), yet the same state in `developers/probe_double_scrollbar.py`
            # [EN] **can** measure that 8px framework bar (x1503..1510). That is, it depends on render timing.
            # [EN] → The "two bars" regression is handled by the **deterministic** A11 / A12 / C12 (checking the
            # [EN] `scroll` mode):
            # [EN] the counterexample method measured that those three go red (53/56), good enough.
        else:
            ok('C13 车道里的自绘条是细条（3~10px）', False, '量不到对话框外框')

        # ★★ 2026-10-09 重写：**用产品自己的两个数判**，不再写死"16 节/517px/540px"。
        #   老写法把"当前目录放得下"当成一条**永恒事实**写进判据 ——
        #   可"放得下吗"取决于 `pane_h` 与目录节数，两者都会变：
        #   这一轮 `pane_h` 被修（它原来比真实可用高度大了 99px，
        #   导致面板被静默裁掉、条也不出），修完 17 节 × 29px **就超出了** ——
        #   于是老判据红，而产品是对的。判据要判的是**关系**，不是某个数。
        # [EN] ★★ Rewritten on 2026-10-09: **judge using the product's own two numbers**, no longer hardcode
        # [EN] "16 sections/517px/540px".
        # [EN] The old approach wrote "the current directory fits" into the criterion as an **eternal fact** --
        # [EN] but "does it fit" depends on `pane_h` and the number of directory sections, both of which
        # [EN] change:
        # [EN] this round `pane_h` was fixed (it was originally 99px larger than the real available height,
        # [EN] causing the panel to be silently clipped and the bar not to appear); after the fix 17 sections ×
        # [EN] 29px **already exceeds it** --
        # [EN] so the old criterion went red while the product was right. A criterion should judge the
        # [EN] **relationship**, not some number.
        _th = thumb_of(toc_bar)
        _rows_n = len(app._ui_help.get('rows') or [])
        _row_h = app._ui_help.get('toc_row_h')
        _avail = app._ui_help.get('toc_avail')
        _need = (_row_h is not None and _avail is not None
                 and _rows_n * _row_h > _avail)
        report['toc_geom'] = {'rows': _rows_n, 'row_h': _row_h,
                              'avail': _avail, 'need': _need,
                              'visible': bool(getattr(_th, 'visible', False))}
        ok('C7 ★★ 左栏条的显隐**与产品自己的判断一致**'
           '（内容高 > 可用高 ⇔ 露条 —— 用产品交出来的两个数判，不自己算）',
           bool(getattr(_th, 'visible', False)) is bool(_need),
           str(report['toc_geom']))

        # 内容多于容器时左栏要自动露条 —— 用检索把命中行数变多来造这个场景
        # （走真实接线：`search.on_change` 正是界面上敲字会走的那一行）。
        # [EN] When content exceeds the container, the left column should show the bar automatically -- use
        # [EN] search to increase the number of matching lines to create this scenario
        # [EN] (goes through real wiring: `search.on_change` is exactly the line the UI goes through when
        # [EN] typing).
        search = app._ui_help.get('search')
        ok('C8 检索框在手（用来造"目录很长"的场景）', search is not None)
        n_rows = len(app._ui_help.get('rows') or [])
        if search is not None:
            search.value = '的'
            search.on_change(type('E', (), {'control': search})())
            page.update()
            await asyncio.sleep(0.7)
            n_rows2 = len(app._ui_help.get('rows') or [])
            ok('C9 检索后目录行数变了（场景成立）', n_rows2 != n_rows or n_rows2 > 0,
               f'{n_rows} → {n_rows2}')
            need = n_rows2 * _TOC_H > (G.HELP_PANE_H - G.SET_H - 10 - 12)
            ok('C10 ★ 左栏判据与真实行数一致：行数×行高 > 容器内高 时才露条',
               thumb_of(toc_bar).visible is bool(need),
               f'{n_rows2} 行 × {_TOC_H:.1f}px vs 容器内高 '
               f'{G.HELP_PANE_H - G.SET_H - 10 - 12}px → 期望 {need}，'
               f'实测 {thumb_of(toc_bar).visible}')
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.3)
    except Exception:                                        # noqa: BLE001
        report['help_reader_fatal'] = traceback.format_exc()
        ok('C1 「翻」页的两条都挂上了（body_bar / toc_bar）', False,
           '崩溃，见报告 help_reader_fatal')

    # ── ② 开卷摄取：左（运行日志）+ 右（AI 优化对话）────────────
    # [EN] ── ② Ingest: left (run log) + right (AI optimization chat) ────────────
    try:
        src = tmp / '雨夜来客'
        (src / '正文').mkdir(parents=True, exist_ok=True)
        (src / '大纲.md').write_text(
            '# 大纲\n\n起：雨夜来客打破平静。\n承：旧事被翻出。\n', encoding='utf-8')
        (src / '人物设定.md').write_text(
            '# 人物\n\n## 主角\n掌柜，沉默寡言。\n\n## 阿枝\n伙计，嘴上不饶人。\n',
            encoding='utf-8')
        (src / '正文' / '第1章.md').write_text(
            '# 第1章\n\n雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。\n' * 10,
            encoding='utf-8')

        app._wizard_path = str(src)
        app._wizard_name = '滚动条UI'
        app._wizard_opts['ai_optimize'] = True
        VU.disable_source_repair(app)        # 那一步会停下来等点击（脚本里跳过）
        # [EN] That step stops and waits for a click (skipped in script)
        app._do_import(page)

        st = app._ingest_state
        ui = {}
        # ① 先等"交给 AI 之前"的确认面板 —— 它把 `panes` 藏起来（版面让给清单），
        #    那期间两栏的条**根本不在屏幕上**，量了必然是 0（第一版就栽在这儿）。
        # [EN] ① First wait for the "before handing to AI" confirmation panel —— it hides `panes` (layout gives
        # [EN] way to the list),
        # [EN] During that time the bars in both columns **are not on screen at all**, so measuring them will
        # [EN] inevitably be 0 (the first version tripped on exactly this).
        for _ in range(80):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            if ui and bool(getattr(ui.get('consent_panel'), 'visible', False)):
                break
        report['consent_shown'] = bool(getattr(ui.get('consent_panel'), 'visible', False))
        if ui.get('consent'):
            ui['consent'](True)                  # 同意 → 管线继续
        # ② 再等 AI 对话阶段（管线在这里停下等作者打字，界面是静止的）
            # [EN] Agree → pipeline continues
            # [EN] ② Then wait for the AI chat phase (the pipeline stops here waiting for the author to type; the
            # [EN] UI is static)
        for _ in range(120):
            await asyncio.sleep(0.1)
            if st.get('phase') == 'chat':
                break
        report['ingest_phase'] = st.get('phase')
        log_bar = ui.get('log_bar')
        chat_bar = ui.get('chat_bar')
        ok('B9 摄取对话框两栏各有一条自绘条',
           log_bar is not None and chat_bar is not None,
           f'log={log_bar is not None} chat={chat_bar is not None}')
        ok('B10 两条都是「Stack(内容, 4px thumb)」的结构',
           bool(log_bar and bars_in(log_bar)) and bool(chat_bar and bars_in(chat_bar)),
           f'{[bool(bars_in(b)) for b in (log_bar, chat_bar)]}')
        for _nm, _lv in (('左栏（日志）', ui.get('log_list')),
                         ('右栏（对话）', ui.get('chat_list'))):
            if _lv is not None:
                ok(f'B11 {_nm}的车道在 ListView 自己的 padding 里',
                   int(getattr(getattr(_lv, 'padding', None), 'right', 0) or 0) >= 8,
                   getattr(_lv, 'padding', None))

        m1 = await measure(log_bar, 'scrollbars_ingest', '开卷 · 左栏运行日志')
        ok('B12 左栏（运行日志）的条真的画出来了', m1.get('n', 0) >= 20, m1)
        ok('B13 左栏的条是窄条（≤8px）', m1.get('n', 0) >= 20
           and (m1.get('x1', 0) - m1.get('x0', 0)) <= 8, m1)
        m2 = await measure(chat_bar, 'scrollbars_ingest_chat', '开卷 · 右栏 AI 对话')
        ok('B14 右栏（AI 优化对话）的条真的画出来了', m2.get('n', 0) >= 20, m2)
        ok('B15 右栏的条是窄条（≤8px）', m2.get('n', 0) >= 20
           and (m2.get('x1', 0) - m2.get('x0', 0)) <= 8, m2)
        ok('B16 两条都落在各自栏的左半…右半侧（在窗口右半边某个"栏内右缘"）',
           m1.get('n', 0) >= 20 and m2.get('n', 0) >= 20
           and m1.get('x0', 0) < m2.get('x0', 0), f"{m1.get('x0')} < {m2.get('x0')}")
        try:
            ui.get('cancel')()
        except Exception:                                    # noqa: BLE001
            pass
        await asyncio.sleep(0.8)
        try:
            page.pop_dialog()
        except Exception:                                    # noqa: BLE001
            pass
        page.update()
        await asyncio.sleep(0.3)
    except Exception:                                        # noqa: BLE001
        report['ingest_fatal'] = traceback.format_exc()
        ok('B9 摄取对话框两栏各有一条自绘条', False, '崩溃，见报告 ingest_fatal')

    # ── ③ 运行界面：中栏输出 + 左右两栏 ─────────────────────────
    # [EN] ── ③ Run UI: center output + left and right columns ─────────────────────
    try:
        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.8)
        ui = app._ui_run
        nbar = ui.get('narrative_bar')
        ncol = ui.get('narrative')
        ok('B17 运行界面中栏挂上了自绘条', nbar is not None and ncol is not None,
           f'bar={nbar is not None} col={ncol is not None}')
        bars = bars_in(page)
        ok('B18 中栏 + 左右两栏各有条（整屏 ≥3 条）', len(bars) >= 3, len(bars))

        # 接线：叙事一多，条自己出现
        # [EN] Wiring: once narrative grows, the bar appears on its own
        for i in range(12):
            app._push_live_card('第 %d 条测试叙事：雨还在下，堂前的灯又晃了一下。' % i,
                                'narration', 0)
        ok('B19 叙事多起来之后中栏的条自动现身（接线通）',
           thumb_of(nbar).visible is True, thumb_of(nbar).visible)

        m = await measure(nbar, 'scrollbars_run', '运行界面 · 中栏输出')
        ok('B20 中栏的条真的画出来了', m.get('n', 0) >= 20, m)
        ok('B21 中栏的条是窄条（≤8px）且落在右半边',
           m.get('n', 0) >= 20 and (m.get('x1', 0) - m.get('x0', 0)) <= 8
           and m.get('x0', 0) > m.get('w', 0) * 0.4, m)
        report['run_x'] = {'narrative_bar_x': [m.get('x0'), m.get('x1')],
                           'screen_w': m.get('w')}
    except Exception:                                        # noqa: BLE001
        report['run_fatal'] = traceback.format_exc()
        ok('B17 运行界面中栏挂上了自绘条', False, '崩溃，见报告 run_fatal')

    # ── ④ 拾卷三栏 + ⑤ 消息框 ───────────────────────────────────
    # [EN] ── ④ Resume three-column + ⑤ message box ───────────────────────────────
    try:
        from store.project import Project
        from store.runfolder import RunFolder
        proj = Project.create_new(Path(CFG.projects_dir()), '滚动条书')
        # ⚠ **按栏高推算要几张卡**，别写死数字：2026-10-08 拾卷对话框调高
        #   （`SAVE_DLG_H` 560→660），原来那句"6 轮必然溢出"当场失效、
        #   判据假红一条 —— 而产品行为是对的（没溢出就不该画条）。
        #   一张存档卡约 90px，这里留够余量。
        # [EN] ⚠ **Derive card count from column height**, don't hardcode a number: 2026-10-08 the resume
        # [EN] dialog was made taller
        # [EN] (`SAVE_DLG_H` 560→660), the old claim "6 rounds will definitely overflow" immediately became
        # [EN] invalid,
        # [EN] one assertion falsely went red —— while the product behavior was correct (if it doesn't overflow
        # [EN] it shouldn't draw a bar).
        # [EN] One save card is about 90px; leave enough margin here.
        try:
            from gui.app_flet import SAVE_LIST_H as _LH
            _n_saves = int(_LH / 80) + 3
        except Exception:                                        # noqa: BLE001
            _n_saves = 12
        for _r in range(_n_saves):             # 造够轮存档，让两栏真的会溢出
        # [EN] Create enough rounds of saves so the two columns actually overflow
            RunFolder(proj.root, f'第{_r + 1}次模拟2026-10-06-1{_r}-00').create()
        app.show_projects_dialog()
        page.update()
        await asyncio.sleep(0.9)
        dlgs = VU.open_dialogs(page)
        bars = bars_in(dlgs[-1]) if dlgs else []
        ok('B22 拾卷三栏各有条（≥3）', len(bars) >= 3, len(bars))
        saves = app._ui_saves or {}
        # ★ "打开就看得见"：**造够**的存档装进这一档栏高里必然溢出，而这三栏
        #   **没有 auto_scroll**（没人滚过），条只能靠装载时那句 `reset` 出来。
        #   ⚠ 卡数由 `SAVE_LIST_H` 推出来（见上），不写死。
        # [EN] ★ "visible on open": **enough** saves packed into this column height will definitely overflow,
        # [EN] and these three columns
        # [EN] have **no auto_scroll** (nobody has scrolled), so the bar can only appear via the `reset` at
        # [EN] load time.
        # [EN] ⚠ Card count is derived from `SAVE_LIST_H` (see above), not hardcoded.
        ok('B22b 拾卷的「② 存档」栏一打开就自己画了条（不需要先滚一下）',
           bool(saves.get('save_bar')) and thumb_of(saves['save_bar']).visible is True,
           thumb_of(saves.get('save_bar')).visible if saves.get('save_bar') else 'no bar')
        if saves.get('save_bar'):
            m = await measure(saves['save_bar'], 'scrollbars_resume', '拾卷 · ② 存档栏')
            ok('B23 拾卷的条真的画出来了', m.get('n', 0) >= 20, m)
            ok('B24 拾卷的条是窄条（≤8px）', m.get('n', 0) >= 20
               and (m.get('x1', 0) - m.get('x0', 0)) <= 8, m)
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.3)

        for i in range(20):
            app._post_message('滚动条验证用的第 %d 条消息（长一点，好让列表真的溢出）' % i,
                              level='warn')
        app.show_messages_dialog()
        page.update()
        await asyncio.sleep(0.8)
        msgs = app._ui_msgs or {}
        dlgs = VU.open_dialogs(page)
        mbars = bars_in(dlgs[-1]) if dlgs else []
        ok('B25 消息框也有条', len(mbars) >= 1, len(mbars))
        ok('B25b 20 条消息时消息框的条一打开就在（同样没滚过）',
           bool(msgs.get('bar')) and thumb_of(msgs['bar']).visible is True,
           thumb_of(msgs.get('bar')).visible if msgs.get('bar') else 'no bar')
        if msgs.get('bar'):
            m = await measure(msgs['bar'], 'scrollbars_messages', '消息列表')
            ok('B26 消息框的条真的画出来了', m.get('n', 0) >= 20, m)
        page.pop_dialog()
        page.update()
    except Exception:                                        # noqa: BLE001
        report['resume_fatal'] = traceback.format_exc()
        ok('B22 拾卷三栏各有条（≥3）', False, '崩溃，见报告 resume_fatal')

    # ── 收尾 ──
    # [EN] ── Wrap-up ──
    try:
        VU.safe_rmtree(tmp)
    except BaseException:                                    # noqa: BLE001
        pass
    # ★★ 任一「分组异常」都必须算失败 —— 否则是**假绿**：
    #   每个分组自己 `except` 之后只往 report 里写一个 `<组>_fatal`，
    #   而汇总只看 `checks`（= 已经跑到的那些 ok()）。中途崩掉的分组，
    #   它后面那些断言**一条都没进 checks**，于是 `passed == total` 照旧成立、
    #   打印"51/52"甚至"52/52"却什么都没验到。
    #   2026-10-07 实测：C13 因 `bb` 未定义抛 NameError，被打成 help_reader_fatal，
    #   而报告里 `失败项: 0`、退出码也是 0。
    # [EN] ★★ Any "group exception" must count as failure —— otherwise it's a **false green**:
    # [EN] Each group catches its own `except` and only writes one `<group>_fatal` into report,
    # [EN] while the summary only looks at `checks` (= the ok() that already ran). For a group that crashed
    # [EN] midway,
    # [EN] none of the assertions after it **made it into checks**, so `passed == total` still holds,
    # [EN] printing "51/52" or even "52/52" while nothing was verified.
    # [EN] 2026-10-07 observed: C13 threw NameError because `bb` was undefined, got marked as
    # [EN] help_reader_fatal,
    # [EN] while the report showed `失败项: 0` and the exit code was also 0.
    fatals = sorted(k for k in report if k.endswith('_fatal'))
    if fatals:
        for k in fatals:
            ok(f'★ 分组 {k[:-6]} 中途抛异常（结论无效，之后的检查没执行）', False,
               str(report[k]).strip().splitlines()[-1][:120])
    report['checks'] = checks
    report['passed'] = sum(1 for c in checks if c['ok'])
    report['total'] = len(checks)
    report['ok'] = report['passed'] == report['total']
    (OUT / f'scrollbars_report{SUFFIX}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for c in checks:
        print(('  ✓ ' if c['ok'] else '  ✗ ') + c['name'] + (
            f"   [{c['detail']}]" if not c['ok'] else ''))
    print(f"\n{report['passed']}/{report['total']}")
    if fatals:
        print('★ 有分组中途抛异常，结论无效 —— 按失败处理；详见 report 里的 *_fatal')
    await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    try:
        logic_checks()
        ft.run(main)
    except Exception:                                        # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        report.setdefault('checks', checks)
        report['ok'] = False
        (OUT / f'scrollbars_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(report['fatal'])
        exit_now(2)
