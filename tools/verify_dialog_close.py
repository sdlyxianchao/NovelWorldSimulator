# -*- coding: utf-8 -*-
"""验证：**每个对话框都有关闭按钮**，按各系统的习惯摆在标题行的哪一边。

用户原话（2026-10-06）：
「还一个事情：**每个对话框都加上关闭按钮**（如果能调用各个系统自己的关闭按钮和位置最好，
比如 Windows 右上角，Linux 左上角，Mac 左上角等，不行就按照 Windows 风格来 在右上角）」

背景：Flet 的对话框是**程序自己画的浮层**，拿不到系统标题栏那三个按钮，
所以只能自己画一个「×」；位置按各系统习惯摆（见 `dialog_close_side()`）。

四组判据：
  A 纯逻辑：`dialog_close_side()` 在各平台下给哪一边（打桩 `sys.platform`）；
  B 结构：9 个对话框入口**逐个真开一遍** —— 标题行里必须有一个「×」，
    而且摆在被要求的那一边（用 Row 的子控件顺序判，不靠猜坐标）；
  C 真行为：**真点一下那个「×」**，对话框必须关掉（`open_dialogs` 回到 0）；
  D 形态：那个「×」必须是 `ft.Icon`（单色矢量）而不是 emoji 字形
    —— 本项目的老账，见 `mk_icon_btn` 的注释。

跑法：`.venv\\Scripts\\python.exe tools/verify_dialog_close.py`
产出：assets/screenshots/dialog_close_report.json

English:
Verify: **every dialog has a close button**, placed on whichever side of the header row the
respective OS convention dictates.
User's exact words (2026-10-06):
"One more thing: **add a close button to every dialog** (if you can call each system's own close
button and position, that would be best,
e.g. Windows top-right, Linux top-left, Mac top-left, etc.; if not, follow the Windows style and
put it top-right)"
Background: Flet dialogs are **overlays the program draws itself**, they cannot access the three
buttons in the system title bar,
so we can only draw an "×" ourselves; the position follows each OS convention (see
`dialog_close_side()`).
Four groups of criteria:
  A Pure logic: which side `dialog_close_side()` gives on each platform (stub `sys.platform`);
  B Structure: **actually open each of the 9 dialog entry points once** -- the header row must contain an "×",
    and it must be on the required side (judged by the order of Row's children, not by guessing coordinates);
  C Real behavior: **actually click that "×"**, the dialog must close (`open_dialogs` back to 0);
  D Form: that "×" must be an `ft.Icon` (monochrome vector) and not an emoji glyph
    -- this project's old debt, see the comment in `mk_icon_btn`.
How to run: `.venv\\Scripts\\python.exe tools/verify_dialog_close.py`
Output: assets/screenshots/dialog_close_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
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

import gui.app_flet as G  # noqa: E402
from gui.app_flet import NovelWorldApp, dialog_close_side  # noqa: E402
from i18n import set_lang, t  # noqa: E402
from store.project import Project  # noqa: E402
from store.runfolder import RunFolder  # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
ITEMS: list = []


def ok(name: str, cond, detail: str = '') -> bool:
    ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


def close_buttons(root) -> list:
    """树里所有「能点的 × 按钮」（`mk_icon_btn(ft.Icons.CLOSE)` 画出来的那个 Container）。
        English:
    All "clickable × buttons" in the tree (the Container drawn by `mk_icon_btn(ft.Icons.CLOSE)`).
    """
    out = []
    for c in VU.walk(root):
        if not callable(getattr(c, 'on_click', None)):
            continue
        for k in VU.walk(c):
            if isinstance(k, ft.Icon) and str(getattr(k, 'icon', '')) == str(ft.Icons.CLOSE):
                out.append(c)
                break
    return out


def header_row(dlg) -> dict:
    """找到**标题行**：那个同时装着对话框标题和「×」的 `Row`。

    ⚠ 第一版按"树里第一个 `Text`"当标题 —— **错了**，而且错得很隐蔽：
    `VU.walk(dlg)` 会先走到 `dlg.actions`，那儿第一个 `Text` 是按钮上的「关闭」，
    于是"标题"变成 `'关闭'`、`header_row` 永远匹配不上 → 那条「× 摆在哪一边」
    的判据**被静默跳过**（`if idx_x and kids:` 直接为假），红不起来也绿得没道理。
    现在改成**结构判据**：认那个"同时有 × 和 21 号标题字"的 `Row`，
    不靠位置，也不靠我自己猜标题是哪一个。
    
        English:
    Find the **header row**: the `Row` that holds both the dialog title and the "×".
        ⚠ The first version treated "the first `Text` in the tree" as the title -- **wrong**, and wrong in a very subtle way:
        `VU.walk(dlg)` visits `dlg.actions` first, where the first `Text` is the "Close" on the button,
        so the "title" becomes `'Close'`, `header_row` never matches -> that "which side is the × on"
        criterion **gets silently skipped** (`if idx_x and kids:` is simply false), so it neither goes red nor goes green for any good reason.
        Now changed to a **structural criterion**: recognize the `Row` that has "both the × and the text of title item 21",
        not relying on position, nor on my own guess about which one the title is.
    """
    for c in VU.walk(dlg):
        if not isinstance(c, ft.Row):
            continue
        kids = list(getattr(c, 'controls', None) or [])
        xs = [i for i, k in enumerate(kids) if close_buttons(k)]
        if not xs:
            continue
        titles = [(i, k) for i, k in enumerate(kids)
                  if isinstance(k, ft.Text)
                  and getattr(k, 'size', None) == G.DLG_TITLE_FS]
        if not titles:
            continue
        return {'kids': kids, 'x_index': xs[0], 'title_index': titles[0][0],
                'title': str(titles[0][1].value or '')}
    return {}


# 9 个对话框入口：(显示名, 方法名, 需要先有项目？)
# [EN] 9 dialog entry points: (display name, method name, requires an existing project first?)
ENTRIES = [
    ('帮助 · 使用说明', 'show_help_dialog', False),
    ('消息历史', 'show_messages_dialog', False),
    ('开卷 · 导入向导', 'show_import_wizard', False),
    ('天机 · 程序设置', 'show_global_settings', True),
    ('拾卷 · 管理项目', 'show_projects_dialog', True),
    ('书斋 · 本书设置', 'show_project_settings', True),
    ('风格参数说明', 'show_style_help_dialog', True),
    ('起　笔', 'show_start_story_dialog', True),
    ('导出 · 打包设定集', 'show_export_dialog', True),
]


async def main(page: ft.Page):
    report: dict = {}
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)

    tmp = Path(tempfile.mkdtemp(prefix='nws_dlgclose_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    try:
        # ══════════ A. 平台 → 哪一边 ══════════
        # [EN] ══════════ A. Platform -> which side ══════════
        real = sys.platform
        got = {}
        for plat, want in (('win32', 'right'), ('darwin', 'left'),
                           ('linux', 'left'), ('freebsd9', 'right')):
            G.sys.platform = plat
            got[plat] = dialog_close_side()
        G.sys.platform = real
        report['sides'] = got
        report['real_platform'] = real
        report['real_side'] = dialog_close_side()
        ok('A：Windows → 右上角（用户点名）', got['win32'] == 'right', got)
        ok('A：macOS → 左上角', got['darwin'] == 'left', got)
        ok('A：Linux → 左上角', got['linux'] == 'left', got)
        ok('A：认不出来的平台按 Windows 来（右上角）', got['freebsd9'] == 'right', got)

        # ══════════ 造一个项目（后 6 个入口要有项目才打得开）══════════
        # [EN] ══════════ Create a project (the last 6 entry points require a project to open) ══════════
        proj = Project.create_new(CFG.projects_dir(), '对话框验证')
        # 「导出」那个入口还要有**一次跑过的模拟**才肯开（没有就只弹一句提示），
        # 所以顺手造一个空的运行文件夹 —— 不然这条判据永远红着，看着像坏了。
        # [EN] The "Export" entry point also requires **a simulation that has been run once** before it will
        # [EN] open (otherwise it just pops up a message),
        # [EN] so just create an empty run folder along the way -- otherwise this criterion stays red forever,
        # [EN] looking broken.
        RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
        app._activate_project(proj)
        app.show_main_screen()
        page.update()
        await asyncio.sleep(1.0)

        # ══════════ B / C / D：逐个真开、真点 ══════════
        # [EN] ══════════ B / C / D: actually open each one, actually click ══════════
        detail: dict = {}
        for label, meth, _need in ENTRIES:
            fn = getattr(app, meth, None)
            if fn is None:
                ok(f'B：{label} —— 还找得到这个入口', False, meth)
                continue
            try:
                fn()
            except Exception as exc:                            # noqa: BLE001
                detail[label] = f'打开时抛错: {exc!r}'
                ok(f'B：{label} 能打开', False, repr(exc))
                continue
            page.update()
            await asyncio.sleep(0.45)

            open_now = [d for d in VU.open_dialogs(page)
                        if not isinstance(d, ft.SnackBar)]
            if not open_now:
                detail[label] = '没打开'
                ok(f'B：{label} 能打开', False, '没有对话框')
                continue
            dlg = open_now[-1]

            # 标题行（结构判据，见 header_row 的注释）
            # [EN] Header row (structural criterion, see the comment in header_row)
            hd = header_row(dlg)
            btns = close_buttons(dlg)
            detail[label] = {
                'title': hd.get('title', ''),
                'n_close': len(btns),
                'side': dialog_close_side(),
                'x_index': hd.get('x_index'), 'n_kids': len(hd.get('kids') or []),
                'is_icon': bool(btns) and all(
                    any(isinstance(k, ft.Icon) for k in VU.walk(b)) for b in btns)}

            ok(f'B：{label} 的标题行里有「×」', len(btns) == 1,
               f'找到 {len(btns)} 个；标题={hd.get("title")!r}')
            ok(f'B：{label} 找到了标题行（标题文字 + × 在同一个 Row 里）',
               bool(hd) and bool(hd.get('title')),
               f'title={hd.get("title")!r} x_index={hd.get("x_index")} '
               f'n_kids={len(hd.get("kids") or [])}')
            ok(f'B：{label} 的标题行只有两件东西（标题 + ×，没混进别的）',
               len(hd.get('kids') or []) == 2, len(hd.get('kids') or []))
            if hd:
                # ★ 顺序就是"摆在哪一边"：Windows 要 × 在最后一个，macOS/Linux 要在第一个
                # [EN] ★ The order is exactly "which side it goes on": Windows needs × last, macOS/Linux need it first
                want_left = dialog_close_side() == 'left'
                last = len(hd['kids']) - 1
                ok(f'B：{label} 的「×」摆在该在的一边'
                   f'（当前平台 → {"左" if want_left else "右"}）',
                   (hd['x_index'] == 0) if want_left else (hd['x_index'] == last),
                   f'× 是第 {hd["x_index"]} 个，标题是第 {hd["title_index"]} 个，'
                   f'共 {last + 1} 个')
            ok(f'D：{label} 的「×」是 `ft.Icon` 矢量（不是 emoji 字形）',
               bool(btns) and all(any(isinstance(k, ft.Icon) for k in VU.walk(b))
                                  for b in btns), str(detail[label]))

            # —— C：真点一下 ——
            # ⚠ Flet 1.0 的 `ft.ControlEvent` 是 `(origin, args, *, inst=True, name=None)`
            #   这种构造方式，手工造一个假事件很别扭、也不是真人点的那条路径的真实形状。
            #   这里直接 `on_click(None)` —— 关闭逻辑**本来就不该依赖事件**
            #   （它先从控件自己身上拿 page），所以这条判据同时钉住了
            #   「点 × 能关」和「不靠事件也能关」。
            # [EN] -- C: really click once --
            # [EN] ⚠ Flet 1.0's `ft.ControlEvent` is constructed as `(origin, args, *, inst=True, name=None)`
            # [EN] This construction makes hand-building a fake event awkward, and it is not the real shape of the
            # [EN] path a real human click takes.
            # [EN] Here we just call `on_click(None)` directly -- the close logic **should never have depended on
            # [EN] the event in the first place**
            # [EN] (it gets the page from the control itself), so this criterion pins down both
            # [EN] "clicking × closes it" and "it can close without relying on the event."
            if not btns:
                ok(f'C：{label} 点「×」之后真的关掉了', False, '没有 × 可点')
                while VU.open_dialogs(page):
                    page.pop_dialog()
                page.update()
                continue
            n_before = len(VU.open_dialogs(page))
            btn = btns[0]
            try:
                btn.on_click(None)
            except Exception as exc:                            # noqa: BLE001
                ok(f'C：{label} 点「×」不该抛错', False, repr(exc))
            page.update()
            await asyncio.sleep(0.5)
            n_after = len(VU.open_dialogs(page))
            ok(f'C：{label} 点「×」之后真的关掉了', n_after < n_before,
               f'{n_before} → {n_after}')

            # 收尾：万一还开着，清干净
            # [EN] Cleanup: in case it is still open, clear it out
            while VU.open_dialogs(page):
                page.pop_dialog()
            page.update()
            await asyncio.sleep(0.25)

        report['dialogs'] = detail
        report['n_entries'] = len(ENTRIES)

        # ══════════ 收尾 ══════════
        # [EN] ══════════ Cleanup ══════════
        n_ok = sum(1 for i in ITEMS if i['ok'])
        report['items'] = ITEMS
        report['ok'] = n_ok == len(ITEMS)
        print(f'\n对话框关闭按钮验证：{n_ok}/{len(ITEMS)}')
    except Exception:                                          # noqa: BLE001
        report['items'] = ITEMS
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
        print(report['fatal'])
    finally:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'dialog_close_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
        VU.safe_rmtree(tmp, ignore_errors=True)
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` raises
        # [EN] CancelledError
        # [EN] to cancel this coroutine; the line `exit_now(...)` after `await shutdown(page)`
        # [EN] **never executes** (exit code is always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 1)


if __name__ == '__main__':
    ft.run(main)
