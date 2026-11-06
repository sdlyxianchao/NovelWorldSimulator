# -*- coding: utf-8 -*-
"""真机验证：**危险确认框的"手打书名"输入框，默认就得看得见**。

用户 2026-10-14 的原话：
    「拾卷的删除小说对话框 高度稍微高一些 把输入小说名字的文本框默认漏出来」

★ 这条为什么值得单独一支判据
------------------------------
改之前它是**一个像素都看不见**的（不是"有点挤"）：
    · 内容区声明 280，实测渲染出来只有 **186**（`developers/probe_del_dialog.py`）；
    · 五行说明的自然高 **222** ⇒ 滚动列 `max_scroll_extent = 35`；
    · 手打框排在**最后一行** ⇒ 默认状态下整块在视口之外。
用户看到的现象是"要求我手打书名，可输入框在哪？" —— 而**确认按钮是灰的**，
不打出书名点不动，于是这个框在用户眼里就是"卡住了"。

修法两件事（判据分别钉住）：
    ① 高度 280 → 330 → **400**（两轮：第一轮"稍微高一些"按短书名拍 330；
       第二轮用**长书名 + 长路径**复现发现 330 在自然高 232 下还滚 25px
       ⇒ 再抬 70 到 400）—— 探针见 `developers/probe_del_dialog_long.py`；
    ② 手打框**移出滚动列**，钉在底部 —— 这是**结构上的保证**：
       书名/路径长短会让上面那几行多折一两行，"刚好够"的高度下次又被埋回去。

分两节：

    A 结构（不起界面）：手打框**不在**滚动列里；`DataTable` 那类"看着在、判据找不到"
      的坑这里不涉及，但**滚动列的子树**是个容易被 `walk` 弄错的地方（它会把
      整棵树都收进来）⇒ A 节用**真机造出来的控件树**判，不是源码字符串。
    B 真机：打开那个框，量「内容区不滚」+「输入框底色像素真的画出来了」+
      成对的两条（框还在 / 输入正确书名后按钮真的解锁）。
    **B4b**（新增）：用**长书名**重开一遍，确认 `max_scroll_extent == 0`
      —— 短书名场景 12/12 全绿但**漏了**用户真实情况
      （`developers/probe_del_dialog_long.py` 是源头）。

★ 判据纪律：期望一律写**绝对字面量**（400 / 0 / 24 / `在这里打出`），
  不 import 产品的 `CONFIRM_BODY_H` —— 变异那个常量时判据的期望会跟着一起动，
  那就成了自证假绿。

产出：assets/screenshots/confirm_dialog_report.json
用法：.venv/Scripts/python.exe tools/verify_confirm_dialog.py

English:
Real-machine verification: the "type the book name" input in the danger confirmation dialog
**must be visible by default**.
User's exact words on 2026-10-14:
    "make the delete-novel dialog in Pickup a bit taller, so the text box for typing the novel
    name shows by default"
★ Why this deserves its own criteria branch
------------------------------
Before the fix it was **not visible at all** (not merely "cramped"):
    · the content area declares 280 but renders only **186** (`developers/probe_del_dialog.py`);
    · the five explanation lines are naturally **222** tall => the scroll column reports
      `max_scroll_extent = 35`;
    · the type box is the **last row** => entirely outside the viewport by default.
What the user saw was "it asks me to type the book name, but where's the input?" -- and the
confirm button is greyed out, so without typing it nothing can be clicked, making the dialog look
"stuck".
The fix is two things (each pinned by a criterion):
    ① height 280 -> 330 -> **400** (two rounds: round one "a bit taller" tuned for **short names**
       and landed on 330; round two reproduced with **long names + long path** to find that 330
       still scrolls 25px when natural is 232 => another 70 -> 400;
       see `developers/probe_del_dialog_long.py`);
    ② the type box **moved out of the scroll column**, pinned to the bottom -- the
       **structural** guarantee: book-name / path length can make those lines wrap an extra line
       or two, and an "exactly enough" height gets buried again.
Two sections:
    A structure (no GUI): the type box is **not** inside the scroll column; judged on the
      **real control tree**, not on source strings.
    B real machine: open that dialog and measure "the content area does not scroll" + "the input's
      background pixels are really painted" + two paired checks (the box still exists / typing the
      right name really unlocks the button).
    **B4b** (added): re-open with a **long name** and check `max_scroll_extent == 0` --
      short-name scenes were 12/12 green but missed the user's real situation
      (`developers/probe_del_dialog_long.py` is the source).
★ Criterion discipline: all expectations are **absolute literals** (400 / 0 / 24 / `在这里打出`),
  never the product's `CONFIRM_BODY_H` -- a mutation of that constant would move the criterion's
  expectation along with it, which is self-confirming fake green.
Output: assets/screenshots/confirm_dialog_report.json
Usage: .venv/Scripts/python.exe tools/verify_confirm_dialog.py
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

import flet as ft                                            # noqa: E402
from PIL import Image, ImageChops                              # noqa: E402

from config import CFG                                       # noqa: E402
CFG.set('MOCK_LLM', 'true')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from gui.app_flet import NovelWorldApp, DLG_W, C            # noqa: E402
from store.project import Project                            # noqa: E402
from i18n import set_lang, t                                 # noqa: E402
set_lang(_lang)

import verify_ui_common as VU                                # noqa: E402
from util.flet_shutdown import shutdown                      # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

# ── 判据用的**绝对字面量**（不 import 产品的常量，见文件头）──
# [EN] ── **Absolute literals** used by the criteria (do not import product constants; see the
# [EN] file header) ──
HAND_BODY_H = 400        # 手打确认那一档的内容区高度
PLAIN_BODY_H = 250       # 不用手打的普通危险确认
FIELD_H = 24             # `SET_H`（输入框高）
# [EN] `SET_H` (the input's height)
CYAN = '#00ffff'
MAGENTA = '#ff00ff'
#: 输入框底色在截图里至少要有这么多像素 —— 少于此就是"被裁/没画出来"。
#: 实测正常值 3982（1920 宽的窗口）；门限取 400 是**宽松的**（只要"真的露出来"就够，
#: 不去卡它的确切尺寸 —— 那会随字体/DPI 漂）。
# [EN] : The input's background must have at least this many pixels in the screenshot -- fewer
# [EN] means "clipped / not painted". Measured normal value is 3982 (on a 1920-wide window); the
# [EN] threshold of 400 is **lenient** (just "it really shows"; do not pin its exact size, which
# [EN] drifts with fonts/DPI).
FIELD_PIX_MIN = 400


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:300]})
    if not cond:
        report['ok'] = False
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'  | {str(detail)[:120]}' if detail and not cond else ''), flush=True)
    return bool(cond)


def _sub(root, target) -> bool:
    """`target` 在不在 `root` 的子树里（含自身）。
        English:
    Whether `target` is inside `root`'s subtree (including itself).
    """
    return any(x is target for x in VU.walk(root))


def _bbox(im, rgb, tol=40):
    h = str(rgb).lstrip('#')
    ref = Image.new('RGB', im.size, tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
    d = ImageChops.difference(im.convert('RGB'), ref)
    r, g, b = d.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    box = mx.point(lambda v: 255 if v <= tol else 0, mode='1').getbbox()
    return None if not box else (box[0], box[1], box[2], box[3],
                                 box[2] - box[0], box[3] - box[1])


async def test_gui(page) -> None:
    import verify_ui_common as VU2

    page.enable_screenshots = True
    page.update()
    tmp = Path(tempfile.mkdtemp(prefix='nws_confirmdlg_'))
    VU2.isolate_projects_dir(tmp / 'Projects')
    proj = Project.create_new(CFG.projects_dir(), '判据用书')
    app = NovelWorldApp()
    app.main(page)
    await asyncio.sleep(1.5)
    app.current_project = proj
    app.show_projects_dialog()
    await asyncio.sleep(1.2)

    root = (VU2.open_dialogs(page) or [page])[-1]
    btn = next((c for c in VU.walk(root)
                if isinstance(c, ft.Container)
                and str(getattr(c, 'tooltip', '') or '') == t('删除这本小说')), None)
    ok('B0 ★★ 拾卷左栏那本书上找得到垃圾桶（用户点的是它）',
       btn is not None, '')
    if btn is None:
        return
    btn.on_click(None)
    await asyncio.sleep(1.2)

    dlg = (VU2.open_dialogs(page) or [None])[-1]
    ok('B0b ★★ 点垃圾桶真的弹出了那个确认框',
       dlg is not None and any('删掉整本小说？' in x
                               for x in VU2.all_texts(dlg)), '')

    # ⚠ 标签在 `mk_field` 返回的 **Row 左边的 Text** 上，真输入框挂在 `Row._field`
    # [EN] ⚠ The label is on the **left Text of the Row** returned by `mk_field`; the real field
    # [EN] hangs on `Row._field`
    row = next((c for c in VU.walk(dlg)
                if isinstance(c, ft.Row)
                and getattr(c, '_field', None) is not None
                and any('在这里打出' in str(getattr(x, 'value', '') or '')
                        for x in VU.walk(c))), None)
    fld = getattr(row, '_field', None)
    ok('B1 ★★★ 那个"在这里打出「书名」以确认"的输入框**还在**'
       '（成对：别为了让它"露出来"把框挪没了）',
       fld is not None, '')

    # 含手打框、且**自带固定高**的那层容器（取最内层 = 真正的 `body`）
    # [EN] The container that contains the type box **and has a fixed height** (take the innermost =
    # [EN] the real `body`)
    boxes = [] if row is None else [
        c for c in VU.walk(dlg)
        if isinstance(c, ft.Container) and c.height not in (None,)
        and _sub(c, row)]
    body = min(boxes, key=lambda c: len(list(VU.walk(c)))) if boxes else None
    ok('B2 ★★★ 内容区高度就是**手打那一档的 400**（两轮加高：第一轮按短书名 330、'
       '第二轮按长书名复现发现还滚 ⇒ 再抬到 400）',
       body is not None and body.height == HAND_BODY_H,
       f'实际 {None if body is None else body.height}')

    cols = [c for c in VU.walk(body) if isinstance(c, ft.Column)
            and c.scroll is not None] if body is not None else []
    col = min(cols, key=lambda c: len(list(VU.walk(c)))) if cols else None
    ok('B3 ★★★ 手打框**不在滚动列里**（结构保证：上面折多少行都埋不住它）',
       col is not None and not _sub(col, row),
       f'滚动列 {len(cols)} 个；它在滚动列里 = '
       f'{None if col is None else _sub(col, row)}')

    # ── 内容区到底滚不滚（滚动条自己报的数）──
    # [EN] ── Does the content area scroll at all (the scrollbar's own report) ──
    got: dict = {}

    def _on(e):
        got.update({'max': e.max_scroll_extent, 'vp': e.viewport_dimension})

    if col is not None:
        col.on_scroll = _on
        page.update()
        await asyncio.sleep(0.3)
        try:
            await col.scroll_to(offset=100)
        except Exception:                                      # noqa: BLE001
            pass
        page.update()
        await asyncio.sleep(0.7)
        try:
            await col.scroll_to(offset=0)
        except Exception:                                      # noqa: BLE001
            pass
        page.update()
        await asyncio.sleep(0.5)
    ok('B4 ★★★ 加高之后内容区**一点都不用滚**'
       '（`max_scroll_extent == 0` —— 自己报的数，不靠找灰带）',
       got.get('max') == 0, f'实测 {got}')

    # ── 涂色：输入框到底画出来没有 ──
    # ⚠ 这一步是**这条诉求的本体**："露出来"本来就是视觉的，只能按像素判。
    # [EN] ⚠ This step is **the heart of this request**: "shows" is inherently visual, so it can
    # [EN] only be judged by pixels.
    if fld is not None:
        fld.bgcolor = MAGENTA
    body_bg_before = None if body is None else body.bgcolor
    if body is not None:
        body.bgcolor = CYAN
    page.update()
    await asyncio.sleep(0.8)
    im = None
    try:
        data = await page.take_screenshot()
        if data:
            shot = OUT / 'confirm_dialog_field.png'
            shot.write_bytes(data)
            im = Image.open(shot).convert('RGB')
    except Exception:                                          # noqa: BLE001
        traceback.print_exc()
    # 还原涂色，别污染后面的判据（B8/B9 还要看这个框）
    # [EN] Restore the painted colours so later criteria are not polluted (B8/B9 still look at this
    # [EN] box)
    if body is not None:
        body.bgcolor = body_bg_before
    if fld is not None:
        fld.bgcolor = C['input_bg']
    page.update()

    if im is None:
        ok('B5 ★★★ 默认状态下输入框**真的画出来了**（截图取不到 ⇒ 判不了，算红）',
           False, 'take_screenshot 没拿到图')
    else:
        h = MAGENTA.lstrip('#')
        tgt = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        n = sum(1 for px in im.getdata() if px == tgt)
        bb = _bbox(im, MAGENTA)
        ok('B5 ★★★ 默认状态下输入框**真的画出来了**'
           '（改之前实测 0 个像素 —— 整块在视口外）',
           n >= FIELD_PIX_MIN,
           f'底色像素 {n}（门限 {FIELD_PIX_MIN}）；bbox={bb}')
        ok(f'B6 ★★ 它**没有被裁**（可见高接近 {FIELD_H}，不是只露一条边）',
           bb is not None and bb[5] >= FIELD_H - 4,
           f'可见高 {None if bb is None else bb[5]} / 标称 {FIELD_H}')
        bb_body = _bbox(im, CYAN)
        if bb_body is not None and bb is not None:
            ok('B7 ★★ 它整个落在内容区里（底边不越过内容区下沿）',
               bb[3] <= bb_body[3] + 2,
               f'输入框底 {bb[3]} / 内容区底 {bb_body[3]}')

    # ── 成对：手打框**还得是有用的**（改了结构别把联动弄坏）──
    # [EN] ── Paired: the type box **must still be useful** (don't break the wiring while
    # [EN] changing the structure) ──
    confirm_btn = next((c for c in VU.walk(dlg)
                        if type(c).__name__ == 'FilledButton'
                        and VU.text_of(c).strip() == t('确认删除')), None)
    ok('B8 ★★ 确认按钮初始是**灰的**（没打书名不许删整本）',
       confirm_btn is not None and bool(confirm_btn.disabled), '')
    if confirm_btn is not None and fld is not None:
        fld.value = '判据用书'
        try:
            fld.on_change(None)
        except Exception:                                      # noqa: BLE001
            pass
        page.update()
        await asyncio.sleep(0.4)
        ok('B9 ★★★ 打出正确书名之后按钮**真的解锁**'
           '（结构改了，这条联动最容易悄悄断掉）',
           not confirm_btn.disabled, f'disabled={confirm_btn.disabled}')
        fld.value = '错的名字'
        try:
            fld.on_change(None)
        except Exception:                                      # noqa: BLE001
            pass
        page.update()
        await asyncio.sleep(0.4)
        ok('B9b ★★ 打错名字又**锁回去**（成对：别写成"只要打过字就解锁"）',
           bool(confirm_btn.disabled), f'disabled={confirm_btn.disabled}')

    # ── B4b：长书名场景下也**一点都不用滚** ──
    # 短书名场景 12/12 全绿但**漏了**用户真实情况（他自己的项目多半是长名/长路径）——
    # 探针 `developers/probe_del_dialog_long.py` 复现：自然高 232、330 时 `max=25`。
    # 330 → 400 之后必须用**同一个**同款场景重测一遍 ⇒ `max=0` 才算真正修好。
    # ★ 短项目判据走完后，**关掉当前 dlg** 重开拾卷 + 用**长名项目**重弹一次。
    #   B5/B6/B7/B8/B9 都依赖短项目 dlg，所以这段**必须放最后**。
    # [EN] ── B4b: even with a long book name **no scrolling at all** ──
    # [EN] Short-name scene was 12/12 green but **missed the user's real case** (his own project
    # [EN] most likely has long name / path) -- the probe `developers/probe_del_dialog_long.py`
    # [EN] reproduced: natural 232, at 330 `max=25`. After 330 -> 400 we have to retest **with the
    # [EN] same long-name scene** => `max=0` to count as truly fixed.
    # [EN] ★ After short-name checks, **dismiss current dlg** and re-open Pickup with a **long-name
    # [EN]   project** to repeat the same scroll. B5/B6/B7/B8/B9 all depend on the short-name dlg,
    # [EN]   so this **must be last**.
    try:
        page.pop_dialog()
        await asyncio.sleep(0.5)
    except Exception:                                          # noqa: BLE001
        pass
    long_proj = Project.create_new(CFG.projects_dir(), '长书名测试' * 6)
    app.show_projects_dialog()
    await asyncio.sleep(1.2)
    long_root = (VU.open_dialogs(page) or [page])[-1]
    long_del_btn = None
    # ★ `_build_novel_card` 把 card 上挂了 `_proj`（`card._proj = proj`，L14065）——
    #   但 `show_projects_dialog` 内部调 `scan_projects(CFG.projects_dir())` —— **每次**
    #   都重新构造 Project 对象，所以 `card._proj` 跟判据这边 `create_new` 出来的
    #   **不是同一个对象**（属性一样、id 不同）。比较 `is` 必然扑空。
    #   ⇒ 用 **`proj.root` 路径字符串**比（项目根 = 一本书 = 唯一）。
    # [EN] ★ `_build_novel_card` hangs `_proj` on the card (`card._proj = proj`, L14065) --
    #   but `show_projects_dialog` calls `scan_projects(CFG.projects_dir())` internally, which
    #   **reconstructs** Project objects every time. So `card._proj` and the `create_new` here are
    #   **not the same object** (same attributes, different ids). `is` always misses.
    #   => Compare **`proj.root` path strings** instead (project root = one book = unique).
    long_card = next((c for c in VU.walk(long_root)
                      if isinstance(c, ft.Container)
                      and getattr(c, '_proj', None) is not None
                      and str(getattr(c._proj, 'root', '')) == str(long_proj.root)), None)
    if long_card is not None:
        long_del_btn = next((c for c in VU.walk(long_card)
                             if isinstance(c, ft.Container)
                             and c.tooltip == t('删除这本小说')), None)
    else:
        long_del_btn = None
    ok('B4b_pre ★ 拾卷左栏那个**长书名**项目上找得到垃圾桶',
       long_del_btn is not None,
       '（没找到 ⇒ 这一节跑不了，B4b 算红）' if long_del_btn is None else '')
    if long_del_btn is not None:
        long_del_btn.on_click(None)
        await asyncio.sleep(1.0)
        long_dlg = (VU.open_dialogs(page) or [None])[-1]
        # 滚动条自报
        got2: dict = {}
        long_cols = [c for c in VU.walk(long_dlg)
                     if isinstance(c, ft.Column) and c.scroll is not None] if long_dlg else []
        long_col = (min(long_cols, key=lambda c: len(list(VU.walk(c))))
                    if long_cols else None)
        if long_col is not None:
            def _on2(e):
                got2.update({'max': e.max_scroll_extent,
                             'vp': e.viewport_dimension})
            long_col.on_scroll = _on2
            page.update()
            await asyncio.sleep(0.3)
            try:
                await long_col.scroll_to(offset=100)
            except Exception:                                  # noqa: BLE001
                pass
            page.update()
            await asyncio.sleep(0.6)
            try:
                await long_col.scroll_to(offset=0)
            except Exception:                                  # noqa: BLE001
                pass
            page.update()
            await asyncio.sleep(0.4)
        ok('B4b ★★★ 长书名（用户真实场景）下也是**一点都不用滚**'
           '（`max_scroll_extent == 0` —— 这是 330→400 这轮加高的真理由）',
           got2.get('max') == 0, f'实测 {got2}')


def main() -> int:
    report['ok'] = True

    async def entry(page) -> None:
        try:
            await test_gui(page)
        except BaseException:                                  # noqa: BLE001
            traceback.print_exc()
            ok('真机段自己跑通', False, traceback.format_exc().splitlines()[-1])
        report['n_ok'] = sum(1 for i in report['checks'] if i['ok'])
        report['n_all'] = len(report['checks'])
        (OUT / 'confirm_dialog_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\n危险确认框（手打书名）验证：{report['n_ok']}/{report['n_all']}")
        await shutdown(page, code=0 if report.get('ok') else 2)

    ft.run(entry)
    return 0


if __name__ == '__main__':
    sys.exit(main())
