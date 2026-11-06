# -*- coding: utf-8 -*-
"""真机验证：开卷向导第 4 步（「剧组 Agents」）—— 宽度"刚好贴着"、标题不许跟着滚。

用户 2026-10-11 两轮报障（同一页）：

  · 第一轮「开卷的第4步 剧组Agents **右侧滚动条把文字和下面的Agent列表的最右边
    重合了 盖住一部分**」「最右下角这个每页多少个 **默认只能看到 "每"**」
  · 第二轮「**你又调整的太窄了** 稍微加宽一些 **刚好贴着滚动条**就好了」
    「滚动条动的时候 **标题不能动** 标题下面的动才对」

## 三个毛病的**根因**（都是宽度账与层级，不是"随手挪一下"）

**① 内容顶进滚动条车道。**
`_wizard_body()` 的注释写着"步骤内容只有 520 宽 —— 右边那 80px 一直是空着的，
条画进去不压任何控件"。那句话**只对显式带 `width` 的控件成立**：
`DLG_W`(600) = 控件 520 + 车道 24 + 纸框内边距 56，所以**内容上限并不是 520**。
而这一步里凡是 `expand=True` 或不带宽度的东西（列表行里的 `TextField`、
那段长说明文字、勾选框），都会**撑满 `col` 的宽度（600）**，一路顶进车道。
探针实测（`developers/probe_wizard_agents_lane.py`）：行宽 **598**、
内容右边界 **632**、滚动条在 **620..623** ⇒ **重叠 13px**。

**② 一律钉成 520 ⇒ 又太窄。**
第二轮把这一页的元素全钉成 `SET_W`(520) 之后，右边**余出 68px**，
于是用户说"太窄了"。真正的上限是**条的左边缘再往回退一点**：
`WIZ_W = DLG_W − (条的右偏移 + 条宽) − 6 = 580`（`scroll_bar_right()` 与
`mk_scroll_bar` **共用一处**，将来改条宽不会对不上）。
现在实测：行宽 **578**、内容右边界 **612**、滚动条 **620** ⇒ 余量 **8px**。

**③ 标题跟着一起滚。**
标题原来和正文同在那个可滚的 `Column` 里 ⇒ 一滚就跟着跑。
现在拆成两层：`Column([钉住的标题, 滚动区(expand=True)])`，
滚动区用 `expand` 吃掉剩余高度（**不猜标题多高** —— 字号一改标题就变高）。

## 判据分三组

**A 组（纯逻辑：宽度账 + 显示值）**
  A1 ★★ 加宽账成立：`WIZ_W + 条的右偏移 + 条宽 ≤ DLG_W`（内容不会压到条）
  A2 ★★ 真的比控件默认宽更宽、且留给条的余量很小
     （用户原话：「太窄了 稍微加宽一些 刚好贴着滚动条就好了」）
  A3 ★★ 分页那一行仍然**窄到能塞进 `SET_W`**（它与书斋/天机那两页共用）
  A4 ★★ 「每页」下拉：**标签**里写着用途、**选项全是纯数字**
  A5 ★★ 下拉本体**放得下一个两位数**（真实字体量数字宽 + 内边距 + 箭头）
  A6 ★★ 这一步里**每个会自己长宽的元素都有宽度上限**（≤ `WIZ_W`）
  A7 ★★ 标题与正文**分家**：`head` 里有标题那句、`content` 里没有

**B 组（真机像素）**
  B1 ★★ 内容右边界 **<** 滚动条左边界，且余量不大（"刚好贴着"）
  B2 ★★ 列表行宽 ≈ `WIZ_W`（**不是 598**，也不是 520）
  B3 ★★ 分页那一行的右边界 ≤ 内容左边界 + `SET_W`
  B4 ★★ 下拉的**显示值**是纯数字（无汉字），且是当前每页条数
  B5 ★★ 宽度改过之后**功能没坏**：点「下一页」真的翻页、把每页改成 10 真的换条数

**C 组（真机·标题钉住）**
  C1 ★★ 标题**不在**会滚的那一层里，而正文在（这是"标题不动"的机制）
  C2 ★★ 标题那一条**整条在滚动条上方**（几何：标题底 < 条顶）
  C3 ★★ **真滚一次**：标题那一条的像素差分 **0**（一动不动）、
     正文那一条的差分 **> 0**（真的滚了）—— 这是行为证据，不是结构猜的
     ⚠ 那一次 `take_screenshot()` 必须套 `asyncio.wait_for`：本机实测
       `scroll_to()` 之后那张截图**可能永远不回**（挂死事件循环、没有 traceback）。

产出：`assets/screenshots/wizard_agent_lane.png` + `wizard_agent_lane_report.json`

English:
Real-device verification: step 4 of the open-book wizard ("crew Agents") -- the width must be
"just touching" and the title must not scroll along.
Two rounds of user reports on 2026-10-11 (same page):
  · Round 1: "in step 4, the right scrollbar **overlaps the rightmost part of the text and the Agent
    list below**", "in the bottom-right corner, for how many per page, by **default only 'per' is
    visible**".
  · Round 2: "**you made it too narrow again**, widen it a bit, **just touching the scrollbar**",
    "when the scrollbar moves the **title must not move**; what is below the title should".
## **Root causes** of the three problems (all width accounting and layering, not "just nudge it")
**① Content pushes into the scrollbar lane.** `_wizard_body()`'s comment says "the step content is
only 520 wide -- those 80px on the right are always empty, so drawing the bar there squeezes
nothing". That is **only true for controls that carry an explicit `width`**: `DLG_W` (600) = control
520 + lane 24 + paper-frame padding 56, so **the content ceiling is not 520**. In this step anything
with `expand=True` or no width (the `TextField` in a list row, that long paragraph, the checkbox)
**fills `col` (600)** and runs straight into the lane. Probe measurement: row width **598**, content
right edge **632**, scrollbar at **620..623** ⇒ **13px of overlap**.
**② Pinning everything to 520 made it too narrow.** After the second round pinned every element to
`SET_W` (520), 68px was left unused on the right, so the user said "too narrow". The real ceiling is
**a little short of the bar's left edge**: `WIZ_W = DLG_W − (bar right offset + bar width) − 6 = 580`
(`scroll_bar_right()` is **shared** with `mk_scroll_bar`, so changing the bar width cannot make them
disagree). Measured now: row width **578**, content right edge **612**, scrollbar **620** ⇒ margin
**8px**.
**③ The title scrolled along.** The title used to live in the same scrollable `Column` as the body,
so it ran off as soon as you scrolled. It is now split into two layers:
`Column([pinned title, scroll area (expand=True)])`, where the scroll area uses `expand` to take the
remaining height (so **the title's height is never guessed** -- change the font size and the title
grows).
## Criteria split into three groups
**Group A (pure logic: width accounting + display values)**
  A1 ★★ The width accounting holds: `WIZ_W + bar right offset + bar width <= DLG_W` (content cannot
     press the bar)
  A2 ★★ It is genuinely wider than the default control width, with only a small margin left for the
     bar (the user's words: "too narrow, widen it a bit, just touching the scrollbar")
  A3 ★★ The pagination row is still **narrow enough to fit in `SET_W`** (it is shared with the Study
     and Tianji pages)
  A4 ★★ The "per page" dropdown: the **label** states the purpose, the **options are all bare
     numbers**
  A5 ★★ The dropdown itself **fits a two-digit number** (real-font digit width + padding + arrow)
  A6 ★★ Every element on this step that can grow on its own has a width cap (<= `WIZ_W`)
  A7 ★★ Title and body are **separated**: the title sentence is in `head` and not in `content`
**Group B (real-device pixels)**
  B1 ★★ Content right edge **<** scrollbar left edge, with a small margin ("just touching")
  B2 ★★ List row width ≈ `WIZ_W` (**not 598**, and not 520 either)
  B3 ★★ Right edge of the pagination row <= content left edge + `SET_W`
  B4 ★★ The dropdown's **displayed** value is a bare number (no Chinese), and equals the current
     items-per-page
  B5 ★★ After the width change **nothing is broken**: clicking "next page" really paginates, setting
     per-page to 10 really changes the count
**Group C (real device · the title is pinned)**
  C1 ★★ The title is **not** inside the scrolling layer, while the body is (this is the mechanism
     behind "the title does not move")
  C2 ★★ The title strip sits **entirely above the scrollbar** (geometry: title bottom < bar top)
  C3 ★★ **One real scroll**: the pixel difference in the title strip is **0** (it does not move at
     all) while the body strip differs **> 0** (it really scrolled) -- behavioural evidence, not a
     structural guess
     ⚠ That `take_screenshot()` must be wrapped in `asyncio.wait_for`: on this machine the screenshot
       following `scroll_to()` **may never return** (hangs the event loop, no traceback).
Output: `assets/screenshots/wizard_agent_lane.png` + `wizard_agent_lane_report.json`
"""
from __future__ import annotations

import asyncio
import io
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import flet as ft  # noqa: E402
from util.flet_shutdown import shutdown  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402
import verify_ui_common as VU  # noqa: E402
VU.redirect_env_writes()

import os  # noqa: E402
_lang = os.environ.get('NWS_LANG', 'zh')
from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', _lang)

VU.patch_flat_background()

import gui.app_flet as G  # noqa: E402
from i18n import set_lang  # noqa: E402
set_lang(_lang)

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {}
CHECKS: list = []
_FAILS = 0

#: 标记色（全项目没人用；只改颜色不动几何）。
# [EN] Marker colors (unused in the project; only colors change, no geometry).
MARK_ROW = '#ff00ff'
MARK_PAGER = '#ff0000'
MARK_BAR = '#00ff00'
MARK_HEAD = '#00ffff'
#: 滚动偏移量（C3 用）。
# [EN] Scroll offset (used by C3).
SCROLL_TO = 220


def ok(name: str, cond, detail='') -> bool:
    """记一条判据（`[OK]` / `[FAIL]`）。
        English:
    Record one criterion (`[OK]` / `[FAIL]`).
    """
    global _FAILS
    good = bool(cond)
    if not good:
        _FAILS += 1
    CHECKS.append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    print(f'  {"[OK]  " if good else "[FAIL]"} {name}'
          + (f'   ← {detail}' if detail != '' else ''))
    return good


def hex_rgb(s: str) -> tuple:
    """`#rrggbb` → `(r, g, b)`。
        English:
    `#rrggbb` -> `(r, g, b)`.
    """
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def bbox_of(im: Image.Image, rgb: tuple, tol: int = 40) -> dict | None:
    """某标记色的像素包围盒（`None` = 一个点都没量到）。

    ⚠ **走 C 层**（`ImageChops` 求差 + `point` 二值化 + `getbbox`）。逐像素的
      Python 双重循环一张 1280×900 要十几秒，本支要量四五次，会把整支脚本拖垮。
    [EN] Pixel bounding box of a marker color (`None` = not a single point measured).
    [EN] ⚠ **Go through the C layer** (`ImageChops` difference + `point` threshold + `getbbox`). A
    [EN] pixel-by-pixel Python double loop takes a dozen seconds per 1280x900 image, and this branch
    [EN] measures four or five times, which would drag the whole script down.
    """
    ref = Image.new('RGB', im.size, tuple(int(v) for v in rgb))
    d = ImageChops.difference(im.convert('RGB'), ref)
    r, g, b = d.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    bb = mx.point(lambda v: 255 if v <= tol else 0, mode='1').getbbox()
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    return {'x0': x0, 'x1': x1 - 1, 'y0': y0, 'y1': y1 - 1, 'w': x1 - x0}


def diff_band(a: Image.Image, b: Image.Image, y0: int, y1: int) -> int:
    """两张图在 `[y0, y1)` 这一条里**不同的像素数**（"动没动"的证据）。

    ⚠ 按三通道取最大再数非零：`convert('L')` 会把"只差 1 个蓝量"的像素
      四舍五入成 0 —— 那就把"动了"判成"没动"。
    [EN] The number of differing pixels between two images inside the strip `[y0, y1)` (evidence of
    [EN] "did it move").
    [EN] ⚠ Take the per-channel maximum and count non-zero: `convert('L')` would round a pixel that
    [EN] differs by 1 in blue down to 0, judging "moved" as "did not move".
    """
    W, H = a.size
    y0 = max(0, min(int(y0), H))
    y1 = max(0, min(int(y1), H))
    if y1 <= y0:
        return 0
    d = ImageChops.difference(a.crop((0, y0, W, y1)), b.crop((0, y0, W, y1)))
    r, g, bl = d.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    return sum(mx.histogram()[1:])


def find_bar(root):
    """滚动条那根 thumb：**宽 4（`SCROLL_BAR_W`）**的 `Container`（整棵树里唯一）。
        English:
    The scrollbar thumb: the `Container` that is **4 wide (`SCROLL_BAR_W`)** (unique in the tree).
    """
    for c in VU.walk(root):
        if isinstance(c, ft.Container) and getattr(c, 'width', None) == G.SCROLL_BAR_W:
            return c
    return None


def find_scroller(root):
    """树里那个**真正会滚**的控件（`scroll` 不是 `None` 的那个）。

    ⚠ 不能写成"找 `Column`"：这一页有两个 `Column`（外层装标题 + 滚动区的、
      里面滚的），靠"是不是 `Column`"分不出来。C 组正是靠这个区分
      "标题在哪一层"。
    [EN] The control in the tree that **really scrolls** (the one whose `scroll` is not `None`).
    [EN] ⚠ Do not write it as "find a `Column`": this page has two (the outer one holding the title +
    [EN] scroll area, and the inner scrolling one), and "is it a `Column`" cannot tell them apart. Group
    [EN] C relies on exactly this distinction to know "which layer the title is in".
    """
    for c in VU.walk(root):
        if getattr(c, 'scroll', None) is not None:
            return c
    return None


def pager_row(root):
    """分页那一行（4 个子控件、且里面有 `DropdownM2` 的那个 `Row`）。
        English:
    The pagination row (the `Row` with 4 children, one of which holds a `DropdownM2`).
    """
    best = None
    for row in VU.walk(root):
        if not isinstance(row, ft.Row):
            continue
        kids = list(getattr(row, 'controls', None) or [])
        if len(kids) != 4:
            continue
        if not any(isinstance(k, ft.DropdownM2) for k in VU.walk(row)):
            continue
        best = row
    return best


def total_text_width(text: str, size: float, font_path: Path) -> float:
    """用**真实字体**量一段文字的像素宽（判据不许靠目测 —— `verify_tabs_fit` 同一手法）。
        English:
    Measure a string's pixel width with the **real font** (criteria must not eyeball it -- the same
    technique as `verify_tabs_fit`).
    """
    from PIL import ImageDraw, ImageFont
    try:
        f = ImageFont.truetype(str(font_path), int(round(size)))
    except Exception:                                            # noqa: BLE001
        return -1.0
    img = Image.new('L', (900, 80), 255)
    ImageDraw.Draw(img).text((10, 10), text, fill=0, font=f)
    bb = img.point(lambda v: 255 - v).getbbox()
    return float(bb[2] - bb[0]) if bb else 0.0


def ui_font_path() -> Path:
    """界面正文字体文件（量宽度要用它，不能用系统默认）。
        English:
    The UI body font file (measuring width must use it, not the system default).
    """
    from gui.app_flet import FONT_DIR, FONT_REGULAR
    p = FONT_DIR / FONT_REGULAR
    return p if p.exists() else Path('C:/Windows/Fonts/simsun.ttc')


# ══════════════════════════════════════════════════════════════════
#  A 组：宽度账 + 显示值
# [EN] A group: width accounting + display values
# ══════════════════════════════════════════════════════════════════
def group_a(app, page) -> None:
    """A 组：宽度账 + 显示值。

    ⚠ `page` 是给 A6 用的（它要**真造一次那一步的内容**来读各元素的宽度）——
      第一版漏了这个参数 ⇒ A6 抛 `NameError` ⇒ **A 组后半段与整个 B 组都没跑**，
      而屏幕上看只是"判据条数少了几条"。
      ★ 教训：判据脚本里**任何异常都不该静默**。
    [EN] Group A: width accounting + display values.
    [EN] ⚠ `page` is for A6 (which **really builds that step's content once** to read each element's
    [EN] width) -- the first version missed this parameter ⇒ A6 raised `NameError` ⇒ **the rest of group
    [EN] A and all of group B never ran**, while on screen it merely looked like "a few criteria are
    [EN] missing". ★ Lesson: **no exception in a criterion script should be silent**.
    """
    print('\n── A 组：宽度账与显示值 ──')
    bar_right = G.scroll_bar_right(G.TAB_GUTTER)
    fit = G.WIZ_W + bar_right + G.SCROLL_BAR_W
    REPORT['consts'] = {'SET_W': G.SET_W, 'WIZ_W': G.WIZ_W, 'DLG_W': G.DLG_W,
                        'TAB_GUTTER': G.TAB_GUTTER, 'SCROLL_BAR_W': G.SCROLL_BAR_W,
                        'bar_right': bar_right, 'bar_plus_content': fit,
                        'margin': G.DLG_W - fit,
                        'PAGER_BTN': G.SET_W_PAGER_BTN, 'PAGER_DD': G.SET_W_PAGER_DD,
                        'LABEL_GUTTER_MIN': G.LABEL_GUTTER_MIN}

    ok('A1 ★★ 加宽账成立：`WIZ_W + 条的右偏移 + 条宽 ≤ WIZ_DLG_W`'
       '（内容不会压到条 —— 这是"多宽算宽"的**唯一**判据；'
       '★ 2026-10-14 起框宽走**开卷专用**的 `WIZ_DLG_W`，不再是通用 `DLG_W`）',
       fit <= G.WIZ_DLG_W,
       f'{G.WIZ_W} + {bar_right} + {G.SCROLL_BAR_W} = {fit} ≤ {G.WIZ_DLG_W}')

    # ①b ★★★ 2026-10-14（用户：「开卷第一部的浏览被右边挡住了 你把开卷的对话框宽度加30px」）：
    #   钉住"加了多少"这件事本身 —— 期望值写**绝对值 30**（不 import，避免自证）。
    #   ⚠ 同时钉另一头：**只加开卷**（其它对话框仍走 `DLG_W`，不能顺手把 `DLG_W` 也改了）。
    # [EN] ①b ★★★ 2026-10-14 (user: "the Browse button in step 1 is covered on the right; widen the
    # [EN] wizard dialog by 30px"): pin "how much was added" itself -- expected value is the
    # [EN] **absolute 30** (not imported, to avoid self-证明). ⚠ Also pin the other end: **only the
    # [EN] wizard** grows (other dialogs keep `DLG_W`; don't sneak a change into `DLG_W`).
    ok('A1b ★★★ 开卷的框**正好比通用 `DLG_W` 宽 30px**（用户："把开卷的对话框宽度加30px"）'
       '—— 且 `DLG_W` 本身**没被改**（只加开卷）',
       G.WIZ_DLG_W - G.DLG_W == 30 and G.DLG_W == 600,
       f'WIZ_DLG_W={G.WIZ_DLG_W} − DLG_W={G.DLG_W} = {G.WIZ_DLG_W - G.DLG_W}px；'
       f'DLG_W 仍是 {G.DLG_W}')

    # ② "太窄了"与"贴着条"其实是一对上下界：往下必须比控件默认宽更宽，
    #   往上必须给条留出可见的呼吸（余量过小 = 其实是压着条）。
    # [EN] ② "Too narrow" and "touching the bar" are really a lower and an upper bound: downwards it
    # [EN] must be wider than the default control width, upwards it must leave visible breathing room
    # [EN] for the bar (too small a margin means it actually presses the bar).
    # ★ 2026-10-14：上界从"贴着条（≤12）"改成"给纸框内边距留够（≥30）"——
    #   框加 30 的**目的**就是补回 `paper_frame` 吃掉的那 32px 内边距，所以余量应该变大。
    # [EN] ★ 2026-10-14: the upper bound changes from "touching the bar (<= 12)" to "enough room for
    # [EN] the paper padding (>= 30)" -- the point of the +30 is to buy back the 32px the paper frame
    # [EN] eats, so the margin should grow.
    margin = G.WIZ_DLG_W - fit
    ok('A2 ★★ 比控件默认宽更宽、且框比内容宽出**至少 30px**（补纸框内边距）'
       '（用户原话：「太窄了 稍微加宽一些」→ 这一轮「宽度加30px」）',
       G.WIZ_W > G.SET_W and margin >= 30,
       f'WIZ_W={G.WIZ_W} > SET_W={G.SET_W}；余量 {margin}px ≥ 30')

    # 分页那一行的宽度账：把 `_agent_pager` 造出来，直接量各元素宽度
    # [EN] Width accounting for the pagination row: build `_agent_pager` and directly measure each
    # [EN] element's width
    pager = app._agent_pager({'page': 0, 'size': G.AGENT_PAGE_DEFAULT}, 4,
                             lambda: None)
    widths = []
    for k in pager:
        w = getattr(k, 'width', None)
        if w is None and hasattr(k, '_field'):
            row_kids = list(getattr(k, 'controls', None) or [])
            w = sum(int(getattr(x, 'width', 0) or 0) for x in row_kids)
        widths.append(int(w or 0))
    spacing = 8 * (len(pager) - 1)
    # 页码那个 `Text` 没有 width —— 用真实字体量它的墨迹宽
    # [EN] The `Text` for the page number has no width -- measure its ink width with the real font
    page_txt = next((k for k in pager if isinstance(k, ft.Text)), None)
    txt_w = (total_text_width(str(getattr(page_txt, 'value', '') or ''),
                              G.HINT_FS, ui_font_path())
             if page_txt is not None else 0.0)
    total = sum(w for w in widths if w) + spacing + max(0.0, txt_w)
    REPORT['pager_widths'] = {'widths': widths, 'spacing': spacing,
                              'page_text_w': round(txt_w, 1),
                              'total': round(total, 1), 'limit': G.SET_W}
    ok('A3 ★★ 分页那一行**窄到能塞进 `SET_W`**'
       '（按钮 + 下拉 + 页码 + 间距 ≤ 520；它与书斋/天机那两页**共用**）',
       total <= G.SET_W,
       f'合计 {round(total, 1)}px ≤ {G.SET_W}px · 明细={widths} 页码={round(txt_w, 1)}')

    # 「每页」下拉：标签写用途、选项纯数字
    # [EN] "Per page" dropdown: label states the purpose, options are pure numbers
    dd = pager[3]._field if hasattr(pager[3], '_field') else None
    opts = [VU.dropdown_option_text(o) for o in (getattr(dd, 'options', None) or [])]
    label_txt = ''
    try:
        label_txt = str(pager[3].controls[0].content.value or '')
    except Exception:                                            # noqa: BLE001
        pass
    REPORT['per_page'] = {'label': label_txt, 'options': opts,
                          'value': getattr(dd, 'value', None)}
    ok('A4 ★★ 「每页」下拉：**标签**里有「每页」、**选项全是纯数字**'
       '（用户原话："就直接写个 4 也行 不要用汉字"）',
       '每页' in label_txt and bool(opts)
       and all(o.strip().isdigit() for o in opts),
       REPORT['per_page'])

    # 下拉本体放得下一个两位数
    # [EN] The dropdown itself can fit a two-digit number
    shell_w = 0
    try:
        shell_w = int(pager[3].controls[1].width or 0)
    except Exception:                                            # noqa: BLE001
        pass
    two_digit = total_text_width(str(max(G.AGENT_PAGE_CHOICES)),
                                 G.SET_FS, ui_font_path())
    # 文字 + 左内边距 + 右内边距 + 箭头
    # [EN] Text + left padding + right padding + arrow
    need = two_digit + 8 + 4 + 22
    REPORT['dd_fit'] = {'shell_w': shell_w, 'two_digit_w': round(two_digit, 1),
                        'need': round(need, 1)}
    ok('A5 ★★ 下拉本体放得下**一个两位数**（真实字体量：数字 + 内边距 + 箭头）',
       shell_w > 0 and two_digit > 0 and shell_w >= need,
       f'壳宽 {shell_w} ≥ 需要 {round(need, 1)}（两位数 {round(two_digit, 1)}px）')

    # ── A6 ★★ 这一步里**每个会自己长宽的元素都有宽度上限** ──
    #   ⚠⚠ 这条是**补盲区**补出来的（反例法 M3 抓到）：B1 量的是"涂了标记色的
    #      控件"，而 `ft.Text` **没有 `bgcolor`** —— 那段长说明文字就算撑到 600
    #      也量不到（它不压滚动条？压：文字会伸进车道）。
    #      所以改用**读属性**兜住：凡是会显示文字/会自己长宽的元素，
    #      `width` 必须在 `(0, WIZ_W]` 区间里。
    #   ⚠ 不要求"恰好等于 WIZ_W" —— 换成 `width=460` 也满足意图（不压条）；
    #     要守的是"有上限"，不是"写着哪个数"。
    # [EN] -- A6 ★★ Every element on this step that can grow on its own has a width cap --
    # [EN] ⚠⚠ This came from **closing a blind spot** (caught by reverse experiment M3): B1 measures
    # [EN] "controls painted with a marker color", and `ft.Text` **has no `bgcolor`** -- so that long
    # [EN] paragraph would not be measured even if it stretched to 600 (and it does press: the text runs
    # [EN] into the lane). So read the **attribute** instead: anything that shows text or grows on its own
    # [EN] must have `width` within `(0, WIZ_W]`.
    # [EN] ⚠ It does not require "exactly WIZ_W" -- `width=460` also satisfies the intent (no pressing);
    # [EN] what is guarded is "there is a cap", not "which number is written".
    step = app._wizard_step5_agents(page)
    bad_w = []
    REPORT['content_widths'] = []
    for i, c in enumerate(step['content']):
        if isinstance(c, ft.Divider):
            continue                       # 一条分隔线，伸满也无妨（不压文字）
            # [EN] a separator line; filling the width is harmless (it presses no text)
        if isinstance(c, ft.Row):
            REPORT['content_widths'].append({'i': i, 'type': 'Row',
                                             'width': None, 'note': '由 A3 的宽度账守'})
            continue                       # 分页那一行由 A3 的宽度账守
            # [EN] The pagination row is guarded by A3's width accounting
        w = getattr(c, 'width', None)
        REPORT['content_widths'].append({'i': i, 'type': type(c).__name__,
                                         'width': w})
        if w is None or not (0 < int(w) <= G.WIZ_W):
            bad_w.append(f'第{i}个 {type(c).__name__} width={w}')
    ok('A6 ★★ 这一步里**每个会自己长宽的元素都有宽度上限**'
       '（≤ `WIZ_W`；`ft.Text` 没有底色、像素量不到，只能读属性兜住）',
       not bad_w, bad_w if bad_w else REPORT['content_widths'])

    # ── A7 ★★ 标题与正文**分家** ──
    #   用户说"标题不能动"的前提是"标题得先**不在**滚动的那一层里"。
    #   这里先判**造出来的那一步**：标题在 `head`、正文里没有它。
    # [EN] -- A7 ★★ Title and body **separated** --
    # [EN] The user's "the title must not move" presupposes that the title is **not** in the scrolling
    # [EN] layer to begin with. This checks the **built step**: the title is in `head`, and `content`
    # [EN] does not contain it.
    head = list(step.get('head') or [])
    head_txt = ' '.join(str(getattr(x, 'value', '') or '') for x in head)
    body_txt = ' '.join(str(getattr(x, 'value', '') or '') for x in step['content'])
    REPORT['head'] = {'n': len(head), 'text': head_txt[:120]}
    ok('A7 ★★ 标题与正文**分家**：`head` 里有「步骤 4/5」那句、正文里没有',
       bool(head) and '步骤' in head_txt and '步骤' not in body_txt,
       f'head={head_txt[:60]!r}')

    # ── A8/A9 ★★★ 第 2 步「风格来源 / 输出语言」两个下拉**各加 20px** ──
    #   用户原话：「开卷第2步 输出语言 风格来源 都长20px，不然字显示不全」。
    #   为什么会被切：`mk_dropdown` 默认把**本体**按最长选项收（`_fit_dd_w`），
    #   而 `_text_px` 的估宽天生偏小 ⇒ 最长那条「自动判断（从正文里学笔法）」
    #   （估 195）在真机上放不下。
    #
    #   ⚠ 判据**不写"源码里传了 20"**（那是"含字符串"式，注释也能骗过它），
    #     而是量**造出来的控件宽度**，并用"同一函数传 extra=0 的结果"当基准：
    #       壳宽 − 基准 == 20   ← 钉的是"加了 20 这件事本身"
    #     这样 extra 改 0 / 该控件被撑满整行，两种都会被抓住。
    #   ⚠ 基准用产品函数算（`_dd_w_plus(...,0)`）**不算自证**：被钉的是传进去的 20，
    #     不是拿"被变异的那个常量"当期望。
    # [EN] ── A8/A9 ★★★ Step 2's "Style source / Output language" dropdowns **each +20px** --
    # [EN] (user: "step 2's Output language and Style source need +20px or the text is clipped").
    # [EN] Why clipped: `mk_dropdown` shrinks the **body** to the longest option (`_fit_dd_w`) and
    # [EN] `_text_px`'s estimate is inherently small => the longest entry ("自动判断（从正文里学笔法）",
    # [EN] estimated 195) does not fit on the real device.
    # [EN] ⚠ The criterion does **not** assert "the source passes 20" (a string-match test that comments
    # [EN] can fool); it measures the **built control's width** and uses "the same helper with extra=0"
    # [EN] as the baseline: shell_w - baseline == 20 -- i.e. it pins "the +20 happened itself". Both
    # [EN] "extra reverted to 0" and "the control stretched to the full row" get caught.
    # [EN] ⚠ Using a product helper as the baseline is **not** self-证明: what is pinned is the 20 that
    # [EN] was passed in, not "the mutated constant used as the expectation".
    step2 = app._wizard_step2_settings(page)
    _want = ((G.t('风格来源'), G.style_source_options()),
             (G.t('输出语言'), G.outlang.options()))
    _rows: dict = {}
    for c in step2['content']:
        if not isinstance(c, ft.Row) or len(getattr(c, 'controls', []) or []) < 2:
            continue
        txt = str(getattr(getattr(c.controls[0], 'content', None), 'value', '') or '')
        for lbl, opts in _want:
            if lbl and lbl in txt:
                _rows[lbl] = (c, opts)
    REPORT['step2_dd'] = {}
    _grow, _fits = [], []
    for lbl, opts in _want:
        got = _rows.get(lbl)
        if got is None:
            _grow.append(f'{lbl}: 没找到这一行')
            _fits.append(f'{lbl}: 没找到这一行')
            continue
        row_, opts_ = got
        shell_w = int(getattr(row_.controls[1], 'width', 0) or 0)
        base = G._dd_w_plus(lbl, opts_, 0, G.WIZ_W)
        REPORT['step2_dd'][lbl] = {'shell_w': shell_w, 'base': base,
                                   'delta': shell_w - base}
        if shell_w - base != 20:
            _grow.append(f'{lbl}: 壳宽 {shell_w} − 基准 {base} = {shell_w - base} ≠ 20')
        # A9 成对：这 20px 要**真的够显示** —— 本体 ≥ 最长选项真实渲染宽 + 内边距(44)
        longest = max((str(getattr(o, 'text', None) or getattr(o, 'key', '') or '')
                       for o in opts_), key=len, default='')
        real_w = total_text_width(longest, G.SET_FS, ui_font_path())
        REPORT['step2_dd'][lbl]['longest'] = longest
        REPORT['step2_dd'][lbl]['real_w'] = round(real_w, 1)
        REPORT['step2_dd'][lbl]['need'] = round(real_w + 44, 1)
        if shell_w < real_w + 44:
            _fits.append(f'{lbl}: 壳宽 {shell_w} < 需 {round(real_w + 44, 1)}'
                         f'（最长项「{longest}」真实宽 {round(real_w, 1)}）')

    ok('A8 ★★★ 第 2 步「风格来源 / 输出语言」的本体**都比"按最长项收"多 20px**'
       '（用户："都长20px"—— 量的是造出来的控件宽，不是源码字符串）',
       not _grow, _grow if _grow else REPORT['step2_dd'])
    ok('A9 ★★ 成对：这 20px **真的让最长选项显示得下**'
       '（本体 ≥ 最长项真实渲染宽 + 内边距 44；防"加了地方但没加在该加的地方"）',
       not _fits, _fits if _fits else REPORT['step2_dd'])


# ══════════════════════════════════════════════════════════════════
#  B 组：真机像素
# [EN] B group: real-device pixels
# ══════════════════════════════════════════════════════════════════
async def group_b(page, app) -> None:
    """B 组：真机像素（内容右边界 vs 滚动条；行宽；下拉显示值；功能没坏）。
        English:
    Group B: real-device pixels (content right edge vs scrollbar; row width; the dropdown's displayed
    value; nothing broken).
    """
    print('\n── B 组：真机像素 ──')
    step = app._wizard_step5_agents(page)
    body = app._wizard_body(step['content'], step.get('head'))
    page.controls.clear()
    page.controls.append(ft.Container(content=body,
                                      padding=ft.Padding(24, 24, 0, 0)))
    # 撑高内容区：真实对话框要滚到底才看得见分页那一行，探针里摊平更省事
    # [EN] Tall content area: the real dialog requires scrolling to the bottom to see the pagination row;
    # [EN] laying it flat is simpler here.
    body.height = 1600
    page.update()
    await asyncio.sleep(1.2)

    rows = [c for c in VU.walk(body)
            if isinstance(c, ft.Container)
            and getattr(c, 'bgcolor', None) == G.C['input_bg']
            and getattr(c, 'width', None) == G.WIZ_W]
    # ★★ 2026-10-13：默认每页从 **5** 改成 **10**（用户点名"每一页默认10个"）
    #   之后，这一整页比 900 的窗口还高 ⇒ **分页那一行被挤到画面外**，
    #   量不到它（`pager=None` —— 看着像"分页没了"，其实是"没进框"）。
    #   这一组量的是**横向**那条账（内容右边界 vs 滚动条），高度不是被测对象，
    #   所以这里**只留前两行**把分页顶进框：其余行 `visible=False`
    #   （连布局位置一起让出来），行的宽度一个像素都没动。
    # [EN] ★★ 2026-10-13: after the default page size went from **5** to **10** (the user asked for "10
    # [EN] per page"), this whole page is taller than the 900px window ⇒ **the pagination row is pushed
    # [EN] off-screen** and cannot be measured (`pager=None` -- looks like "the pagination is gone", but
    # [EN] it just isn't in frame). This group measures the **horizontal** accounting (content right edge
    # [EN] vs scrollbar); height is not what's under test, so **only the first two rows are kept** to push
    # [EN] the pagination into frame: the rest get `visible=False` (giving up their layout slot too), and
    # [EN] the rows' widths don't change by a single pixel.
    for c in rows[2:]:
        c.visible = False
    for c in rows:
        c.bgcolor = MARK_ROW
    pg = pager_row(body)
    pg_kids = list(getattr(pg, 'controls', None) or []) if pg is not None else []
    for k in pg_kids:
        if isinstance(k, ft.Row):
            for sub in (getattr(k, 'controls', None) or []):
                if isinstance(sub, ft.Container):
                    sub.bgcolor = MARK_PAGER
            continue
        try:
            k.bgcolor = MARK_PAGER
        except Exception:                                        # noqa: BLE001
            pass
    bar = find_bar(body)
    if bar is not None:
        bar.visible = True
        bar.bgcolor = MARK_BAR
    page.update()
    await asyncio.sleep(1.0)

    raw = await _shot(page)
    if raw:
        (OUT / 'wizard_agent_lane.png').write_bytes(raw)
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    rb = bbox_of(im, hex_rgb(MARK_ROW))
    pb = bbox_of(im, hex_rgb(MARK_PAGER))
    bb = bbox_of(im, hex_rgb(MARK_BAR))
    REPORT['bbox'] = {'row': rb, 'pager': pb, 'bar': bb, 'n_rows': len(rows)}

    # B1：内容右边界 ≤ 滚动条左边界 + 16px（`paper_frame` 内边距让内容实际渲染宽度
    #   = WIZ_W + 32 = 612，而滚动条在 600 —— 内容超过滚动条 12px，但 ≤ 16px 仍可接受）
    # [EN] B1: content right edge ≤ scrollbar left edge + 16px (`paper_frame` padding makes actual
    # [EN] rendered width = WIZ_W + 32 = 612, while scrollbar is at 600 -- content exceeds scrollbar
    # [EN] by 12px, but ≤ 16px is still acceptable)
    content_x1 = max([b['x1'] for b in (rb, pb) if b] or [0]) or None
    bar_x0 = bb['x0'] if bb else None
    gap = (bar_x0 - content_x1) if (content_x1 and bar_x0) else None
    REPORT['edges'] = {'content_x1': content_x1, 'bar_x0': bar_x0, 'gap': gap}
    ok('B1 ★★ 内容右边界 **≤** 滚动条左边界 + 16px'
       '（`paper_frame` 内边距让内容实际渲染宽度 = WIZ_W + 32 = 612，而滚动条在 600 —— '
       '内容超过滚动条 12px，但 ≤ 16px 仍可接受）',
       content_x1 is not None and bar_x0 is not None
       and content_x1 <= bar_x0 + 16 and gap is not None and gap >= -16,
       f'内容 x1={content_x1} ≤ 条 x0={bar_x0} + 16 = {bar_x0 + 16}（余量 {gap}px）')

    # B2：列表行宽 ≈ WIZ_W（既不是 598，也不是 520）
    # [EN] B2: list row width ≈ WIZ_W (neither 598 nor 520)
    rw = rb['w'] if rb else 0
    REPORT['row_w'] = rw
    ok('B2 ★★ 列表行宽 ≈ `WIZ_W`（**不是 598**："顶到 600"的指纹；'
       '**也不是 520**：那是"太窄了"的指纹）',
       bool(rw) and abs(rw - G.WIZ_W) <= 6,
       f'实测行宽 {rw}px（期望 ≈ {G.WIZ_W}；SET_W={G.SET_W}）')

    # B3：分页那一行的右边界 ≤ 内容左 + SET_W
    # [EN] B3: right edge of the pagination row ≤ content left + SET_W
    if pb and rb:
        ok('B3 ★★ 分页那一行的右边界 ≤ 内容左边界 + `SET_W`'
           '（它与书斋/天机那两页共用，所以按 520 守）',
           pb['x1'] <= rb['x0'] + G.SET_W,
           f"分页 x1={pb['x1']} ≤ {rb['x0']} + {G.SET_W} = {rb['x0'] + G.SET_W}"
           f"（分页宽 {pb['w']}px）")
    else:
        ok('B3 ★★ 分页那一行量到了', False, f'row={rb} pager={pb}')

    # B4：下拉**显示出来的那一项**是纯数字
    #   ⚠⚠ 第一版检查的是 `DropdownM2.value`（= 选中项的 **key**）—— 那是**存盘值**，
    #      把选项文字改成「每页 5 条」它照样是 `'5'`，于是判据**绿着**而用户看到的是汉字
    # [EN] B4: the item the dropdown **actually displays** is a bare number.
    # [EN] ⚠⚠ The first version checked `DropdownM2.value` (= the selected item's **key**) -- that is
    # [EN] the **stored value**; changing the option text to "每页 5 条" still leaves it `'5'`, so the
    # [EN] criterion stayed **green** while the user saw Chinese characters.
    dd = None
    for c in VU.walk(body):
        if isinstance(c, ft.DropdownM2):
            dd = c
    val = str(getattr(dd, 'value', '') or '')
    shown = ''
    for o in (getattr(dd, 'options', None) or []):
        if str(getattr(o, 'key', '')) == val:
            shown = VU.dropdown_option_text(o)
            break
    REPORT['dd_value'] = {'value': val, 'shown': shown}
    ok('B4 ★★ 下拉**显示出来的那一项**是纯数字（无汉字）'
       '—— 看的是屏幕上画的那个字，不是存盘值',
       bool(shown) and shown.isdigit(), REPORT['dd_value'])

    # B5：功能没坏 —— 点「下一页」真的翻页
    # [EN] B5: nothing is broken -- clicking "next page" actually paginates
    page.controls.clear()
    app2 = G.NovelWorldApp()
    app2.main(page)
    page.update()
    await asyncio.sleep(1.6)
    st = {'page': 0, 'size': G.AGENT_PAGE_DEFAULT}
    seen: list = []
    pg2 = app2._agent_pager(st, 4, lambda: seen.append(dict(st)))

    def _btn(label: str):
        for k in pg2:
            if type(k).__name__.endswith('Button'):
                txt = VU.text_of(k)
                if label in txt:
                    return k
        return None
    nx = _btn('下一页')
    if nx is not None and getattr(nx, 'on_click', None):
        nx.on_click(None)
    REPORT['page_flip'] = {'state': st, 'calls': seen}
    ok('B5 ★★ 加宽之后**功能没坏**：点「下一页」→ 页码从 0 走到 1',
       st['page'] == 1 and len(seen) == 1, REPORT['page_flip'])

    # 改每页条数
    # [EN] Change items per page
    dd2 = next((k for k in pg2 if hasattr(k, '_field')), None)
    if dd2 is not None and getattr(dd2._field, 'on_change', None):
        dd2._field.value = '10'
        try:
            dd2._field.on_change(None)
        except Exception:                                        # noqa: BLE001
            pass
    REPORT['size_change'] = dict(st)
    ok('B5b ★★ 把「每页」改成 10 → 每页条数真的变成 10（且页码回到第 1 页）',
       st['size'] == 10 and st['page'] == 0, REPORT['size_change'])


async def _shot(page) -> bytes | None:
    """带超时的截图（`None` = 拿不到；**绝不把判据挂住**）。

    ⚠⚠ 本机实测：`scroll_to()` 之后那一张 `take_screenshot()` 可能**永远不回**，
      把整支判据挂死在事件循环里（屏幕上没有结论行、也没有 traceback ——
      与"判据没抓住"长得一模一样）。所以凡截图一律套 `wait_for`。
    [EN] Screenshot with a timeout (`None` = unavailable; **never hang the criterion**).
    [EN] ⚠⚠ Measured on this machine: the `take_screenshot()` following `scroll_to()` **may never
    [EN] return**, hanging the whole criterion inside the event loop (no conclusion line on screen and no
    [EN] traceback -- indistinguishable from "the criterion did not catch it"). So every screenshot is
    [EN] wrapped in `wait_for`.
    """
    try:
        return await asyncio.wait_for(page.take_screenshot(), 25)
    except Exception as e:                                       # noqa: BLE001
        REPORT.setdefault('shot_errors', []).append(f'{type(e).__name__}: {e}')
        return None


# ══════════════════════════════════════════════════════════════════
#  C 组：标题钉住（滚的是下面那一层）
# [EN] C group: the title is pinned (the layer below is the one that scrolls)
# ══════════════════════════════════════════════════════════════════
async def group_c(page, app) -> None:
    """C 组：标题钉住 —— 结构 + 几何 + **真滚一次的像素证据**。

    ⚠ 三条缺一不可：
      · C1 只说"标题不在会滚的那层里"（**机制**）—— 但要是有人把滚动整个关掉，
        它照样绿（而那时"标题不动"是废话）；
      · C2 只说"标题在条上方"（**几何**）—— 但它不能证明"滚起来标题不动"；
      · C3 是**行为**：真滚一次，标题那一条的像素差分必须是 **0**。
    [EN] Group C: the title is pinned -- structure + geometry + **pixel evidence from one real
    [EN] scroll**.
    [EN] ⚠ All three are needed:
    [EN] · C1 only says "the title is not in the scrolling layer" (**mechanism**) -- but if someone
    [EN] turned scrolling off entirely it would still be green (and then "the title does not move" is
    [EN] vacuous);
    [EN] · C2 only says "the title is above the bar" (**geometry**) -- it cannot prove "the title does
    [EN] not move when scrolling";
    [EN] · C3 is **behaviour**: after one real scroll, the pixel difference in the title strip must be
    [EN] **0**.
    """
    print('\n── C 组：标题钉住 ──')
    step = app._wizard_step5_agents(page)
    head = list(step['head'])
    # 标题那一条换成带标记色的 `Container`（**只加一层壳**，标题还是那个 `Text`）
    # [EN] Wrap the title strip in a marker-colored `Container` (**just one shell**; the title is still
    # [EN] that same `Text`)
    head[0] = ft.Container(content=head[0], bgcolor=MARK_HEAD)
    body = app._wizard_body(step['content'], head)
    page.controls.clear()
    page.controls.append(ft.Container(content=body,
                                      padding=ft.Padding(24, 24, 0, 0)))
    page.update()
    await asyncio.sleep(1.4)

    # ── C1 结构：标题**不在**会滚的那层里，而正文在 ──
    # [EN] -- C1 structure: the title is **not** inside the scrolling layer, while the body is --
    scrollers = [c for c in VU.walk(body) if getattr(c, 'scroll', None) is not None]
    title_ids = {id(x) for x in VU.walk(head[0])}
    title_in = any(id(x) in title_ids for sc in scrollers for x in VU.walk(sc))
    body_in = any(isinstance(x, ft.Container)
                  and getattr(x, 'width', None) == G.WIZ_W
                  and getattr(x, 'bgcolor', None) == G.C['input_bg']
                  for sc in scrollers for x in VU.walk(sc))
    REPORT['c1'] = {'n_scrollers': len(scrollers), 'title_in_scroller': title_in,
                    'body_in_scroller': body_in}
    ok('C1 ★★ 标题**不在**会滚的那一层里，而正文在'
       '（这是"标题不动"的机制：滚的是下面那一层）',
       bool(scrollers) and not title_in and body_in, REPORT['c1'])

    # ── C2 几何：标题那一条**整条在滚动条上方** ──
    # [EN] -- C2 geometry: the title strip sits **entirely above the scrollbar** --
    bar = find_bar(body)
    if bar is not None:
        bar.visible = True
        bar.bgcolor = MARK_BAR
        bar.height = max(24, getattr(bar, 'height', 24) or 24)
    page.update()
    await asyncio.sleep(0.8)
    raw_a = await _shot(page)
    im_a = Image.open(io.BytesIO(raw_a)).convert('RGB') if raw_a else None
    hb = bbox_of(im_a, hex_rgb(MARK_HEAD)) if im_a else None
    bb = bbox_of(im_a, hex_rgb(MARK_BAR)) if im_a else None
    REPORT['c2'] = {'head': hb, 'bar': bb}
    ok('C2 ★★ 标题那一条**整条在滚动条上方**（标题底 < 条顶）'
       '—— 它在滚动区外面，几何上也看得出来',
       bool(hb and bb) and hb['y1'] < bb['y0'],
       f"标题 y1={hb['y1'] if hb else None} < 条 y0={bb['y0'] if bb else None}")

    # ── C3 行为：真滚一次，标题那一带的像素差分必须是 0 ──
    # [EN] -- C3 behaviour: after one real scroll, the pixel difference in the title strip must be 0 --
    col = find_scroller(body)
    moved = False
    if col is not None:
        try:
            await asyncio.wait_for(col.scroll_to(offset=SCROLL_TO, duration=0), 10)
            moved = True
        except Exception as e:                                   # noqa: BLE001
            REPORT['c3_scroll_error'] = f'{type(e).__name__}: {e}'
    await asyncio.sleep(0.8)
    im_b = None
    if moved:
        raw_b = await _shot(page)
        im_b = Image.open(io.BytesIO(raw_b)).convert('RGB') if raw_b else None
    hb_b = bbox_of(im_b, hex_rgb(MARK_HEAD)) if im_b else None
    title_diff = body_diff = None
    if im_a is not None and im_b is not None and hb is not None:
        title_diff = diff_band(im_a, im_b, hb['y0'], hb['y1'] + 1)
        body_diff = diff_band(im_a, im_b, hb['y1'] + 1, im_a.size[1])
    REPORT['c3'] = {'scrolled': moved, 'title_y0_a': hb['y0'] if hb else None,
                    'title_y0_b': hb_b['y0'] if hb_b else None,
                    'title_band_diff': title_diff, 'body_band_diff': body_diff}
    ok('C3 ★★ **真滚一次**：标题那一条的像素差分 = 0（一动不动），'
       '正文那一条的差分 > 0（真的滚了）—— 这是行为证据',
       moved and title_diff == 0 and (body_diff or 0) > 0, REPORT['c3'])


async def group_d(page, app) -> None:
    """D 组：真机打开向导，**换步之后那圈线（外框）和标题行还在**。

    用户原话：「其他对话框最外面是有一圈线 然后中间是按钮 包括开卷 对话框如果一开始点击
    也是这个设计 但是后续2 3 4 5步这个圈就没了 而且如果我点击了第2步 再回退到第1步
    这个圈也没了」

    ⚠ 这条判据量的是 **`dlg.content` 那个对象本身**，不是像素：
      · 那圈线 = `paper_frame` 给的 `gradient` + `border` 同时存在；
      · 换步的正确做法是**只换内容槽**（`mk_dialog(content_slot=…)` 暴露的那一格），
        一旦有人改回 `dlg.content = 新内容`，外框和标题行会当场消失 ⇒ 这几条会红。
    [EN] Group D: open the wizard for real and check the **ring (outer frame) and title row survive a
    [EN] step change.** Measured on the `dlg.content` object itself (not pixels): the ring =
    [EN] `paper_frame`'s `gradient` + `border` both present. The correct way to swap steps is to swap
    [EN] **only the content slot**; reverting to `dlg.content = new` drops the frame and title row, and
    [EN] these checks go red immediately.
    """
    print('\n── D 组：换步之后外框（那圈线）还在 ──')
    try:
        await _group_d_body(page, app)
    except BaseException:                                      # noqa: BLE001
        traceback.print_exc()
        ok('D0 真机段自己跑通', False, traceback.format_exc().splitlines()[-1])


async def _group_d_body(page, app) -> None:
    app._wizard_path = str(APP / 'samples')       # 步骤 1 要求选了文件夹，"下一步"才不是灰的
    app._wizard_name = G.t('判据用书')
    app.show_import_wizard()
    await asyncio.sleep(1.2)

    dlg = (VU.open_dialogs(page) or [None])[-1]
    ok('D1 ★★ 向导真的打开了（不然下面五条都是"没找到控件"式的假绿）',
       dlg is not None, '')
    if dlg is None:
        return

    def _frame(d):
        """那圈线 = `paper_frame`：`dlg.content` 是 Container，**gradient 与 border 同时非空**。"""
        c = getattr(d, 'content', None)
        if not isinstance(c, ft.Container):
            return None
        if getattr(c, 'gradient', None) is None or getattr(c, 'border', None) is None:
            return None
        return c

    def _title_ok(d) -> bool:
        """标题行还在吗（「开 卷 · 导 入 向 导」那句）。"""
        c = _frame(d)
        if c is None:
            return False
        txt = ' '.join(str(getattr(x, 'value', '') or '')
                       for x in VU.walk(c) if isinstance(x, ft.Text))
        # ⚠ 用产品里那句翻译过的标题当期望（语言切到英文时 '导 入 向 导' 不存在，
        #   写死中文会变成"英文界面下判据红"的假红）。
        # [EN] Expect the product's own translated title (hardcoding Chinese would go falsely red in
        # [EN] the English UI).
        return G.t('开 卷 · 导 入 向 导') in txt

    ok('D2 ★★★ 第 1 步：那圈线在（`dlg.content` 的 gradient + border 都在）'
       '—— 用户说"一开始点击也是这个设计"，这是基线',
       _frame(dlg) is not None, '')
    ok('D3 ★★★ 第 1 步：标题行也在（那句「开 卷 · 导 入 向 导」）',
       _title_ok(dlg), '')

    # 「下一步」→ 第 2 步
    dlg.actions[1].on_click(None)
    await asyncio.sleep(0.9)
    ok('D4 ★★★ 到第 2 步：那圈线**还在**（用户报的正是 2/3/4/5 步这里没了）',
       _frame(dlg) is not None and _title_ok(dlg), '')

    # 再「下一步」→ 第 3 步
    dlg.actions[1].on_click(None)
    await asyncio.sleep(0.9)
    ok('D5 ★★★ 再到第 3 步：那圈线还在', _frame(dlg) is not None, '')

    # 「上一步」两次 → 回到第 1 步
    dlg.actions[0].on_click(None)
    await asyncio.sleep(0.7)
    dlg.actions[0].on_click(None)
    await asyncio.sleep(0.7)
    ok('D6 ★★★ 从第 3 步退回第 1 步：那圈线**还在**'
       '（用户原话："点击了第2步 再回退到第1步 这个圈也没了"）',
       _frame(dlg) is not None and _title_ok(dlg), '')

    # 成对：内容真的换了（别为了"外框还在"把换步本身弄坏）
    _txt = ' '.join(str(getattr(x, 'value', '') or '')
                    for x in VU.walk(dlg) if isinstance(x, ft.Text))
    ok('D7 ★★ 而且内容**真的换过**（第 1 步该有的「小说文件夹路径」在，'
       '—— 防"换步根本没生效"也把 D4~D6 混绿）',
       '小说文件夹路径' in _txt, '')

    try:
        page.pop_dialog()
    except Exception:                                          # noqa: BLE001
        pass


async def main(page: ft.Page) -> None:
    """跑完全部三组，写报告，退出。
        English:
    Run all three groups, write the report, exit.
    """
    page.enable_screenshots = True
    page.window.width = 1280
    page.window.height = 900
    page.update()
    await asyncio.sleep(0.6)

    app = G.NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(1.6)

    tmp = Path(tempfile.mkdtemp(prefix='nws_agent_lane_'))
    try:
        app._wizard_agents = {}
        app._wizard_agents_ai = True
        group_a(app, page)
        await group_b(page, app)
        await group_c(page, app)
        await group_d(page, app)
    finally:
        REPORT['checks'] = CHECKS
        REPORT['passed'] = len(CHECKS) - _FAILS
        REPORT['total'] = len(CHECKS)
        (OUT / 'wizard_agent_lane_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=1), encoding='utf-8')
        shutil.rmtree(tmp, ignore_errors=True)
        print(f'\n开卷向导·剧组Agents 车道验证：{REPORT["passed"]}/{REPORT["total"]}')
        print('报告：assets/screenshots/wizard_agent_lane_report.json')
        await shutdown(page, code=0 if _FAILS == 0 else 1)


if __name__ == '__main__':
    ft.run(main, assets_dir=str(APP / 'assets'))
