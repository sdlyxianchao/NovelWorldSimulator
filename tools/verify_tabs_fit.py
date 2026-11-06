# -*- coding: utf-8 -*-
"""判据：**「天机」的六个页签必须全都看得见**（最右边那个不许被挤出去）。

来历（2026-10-10 用户原话）
---------------------------
「天机（全局设置 左右再大一些 **最右侧 Tab 看不见了**）必须所有上面的 Tab
都显示出来」。

根因**不是宽度不够那么简单**（所以"加宽一点"治不了根）：

  ★ **Flet 1.0 的 `TabBar.scrollable` 默认是 `True`** —— 与 Flutter 的默认值相反。
    装不下的时候，它**不换行、也不截断**，而是把多出来的页签推到**可视区之外**。
    于是用户看到的是"右边少了一个页签"，而不是"字被挤扁了" ——
    **前者是静默的，后者看得见**。这一条才是要点：`scrollable` 必须显式关掉。

两手一起：① 加宽对话框（`DLG_W_TABS`）；② 显式 `scrollable=False`。
两边必须配平 —— 对话框宽了，页签内容的车道也要跟着宽（`TAB_LANE_EXTRA`），
否则右边空出一大片纸（本项目对"白空"有专门的一条纪律）。

判据怎么量
----------
用 **PIL + 随附字体本身**（`assets/fonts/LXGWWenKai-Regular.ttf`）量每个页签
标题的字宽 —— 界面字体就是它（`page.theme.font_family = UI_FONT`），
所以这不是拍脑袋的估算。宁可算得保守一点（要求留 ≥ 24px 余量）。

跑法：`.venv/Scripts/python.exe tools/verify_tabs_fit.py`
报告：`assets/screenshots/tabs_fit_report.json`

English:
Assertion: **all six tabs of "Tianji" must be visible** (the rightmost one must not be pushed
out).
Origin (user's exact words on 2026-10-10)
---------------------------
"Tianji (global settings make left and right a bit larger **the rightmost Tab can't be seen**)
all the Tabs above must
all be displayed".
The root cause is **not as simple as insufficient width** (so "widen a bit" won't cure the
root):
  ★ **Flet 1.0's `TabBar.scrollable` defaults to `True`** —— opposite to Flutter's default.
    When it doesn't fit, it **doesn't wrap and doesn't truncate**, but pushes the extra tabs **outside the visible area**.
    So what the user sees is "a tab missing on the right", not "text squeezed flat" ——
    **the former is silent, the latter is visible**. This is the key point: `scrollable` must be explicitly turned off.
Both together: ① widen the dialog (`DLG_W_TABS`); ② explicitly `scrollable=False`.
Both sides must be balanced —— when the dialog is wider, the tab content's lane must widen too
(`TAB_LANE_EXTRA`),
otherwise a large blank sheet appears on the right (this project has a dedicated rule about
"white space").
How the assertion is measured
----------
Use **PIL + the bundled font itself** (`assets/fonts/LXGWWenKai-Regular.ttf`) to measure each
tab
title's text width —— the UI font is exactly this one (`page.theme.font_family = UI_FONT`),
so this is not a rough guess. Better to compute conservatively (require leaving ≥ 24px margin).
How to run: `.venv/Scripts/python.exe tools/verify_tabs_fit.py`
Report: `assets/screenshots/tabs_fit_report.json`
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

REPORT: dict = {'checks': [], 'notes': []}
SRC = APP / 'gui' / 'app_flet.py'
FONT = APP / 'assets' / 'fonts' / 'LXGWWenKai-Regular.ttf'
#: 标签之间还要留的余量（TabBar 自己有内边距、指示条也会占位）。
# [EN] : Extra margin to leave between labels (TabBar has its own padding, and the indicator also takes
# [EN] up space).
MARGIN = 24


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    return bool(cond)


def read(rel: str) -> str:
    return (APP / rel).read_text(encoding='utf-8')


def between(text: str, start: str, end: str = '') -> str:
    i = text.find(start)
    if i < 0:
        return ''
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j if j > 0 else len(text)]


def num(src: str, name: str) -> int:
    m = re.search(rf'(?m)^{name}\s*=\s*(\d+)', src)
    return int(m.group(1)) if m else -1


def tab_labels(block: str) -> list[str]:
    """从 `tab_defs = [...]` 那一块里取页签标题。

    ⚠ 只认**行首那一层**的元素（`            (t("常规"), …),`）——
      直接全文找 `t("…")` 会把每个页签**内部**的小节标题一起捞进来
      （那样"6 个页签"会变成几十个，判据就成了假的）。
    
        English:
    Take the tab titles from the `tab_defs = [...]` block.
        ⚠ Only recognize elements at the **first level of the line** (`            (t("常规"), ...),`) ——
          a direct full-text search for `t("...")` will also scoop up the section titles **inside** each tab
          (that way "6 tabs" becomes dozens, and the assertion becomes fake).
    """
    return re.findall(r'(?m)^ {12}\(t\("([^"]+)"\),', block)


def measure(labels: list[str], size: float, pad: int) -> dict:
    from PIL import ImageFont
    f = ImageFont.truetype(str(FONT), int(round(size)))
    widths = [f.getlength(x) for x in labels]
    need = sum(widths) + pad * 2 * len(labels)
    return {'每页签字宽': [round(w, 1) for w in widths],
            '合计字宽': round(sum(widths), 1),
            '每侧内边距': pad,
            '需要宽度': round(need, 1),
            '明细': {lab: round(w, 1) for lab, w in zip(labels, widths)}}


def test_global_tabs() -> None:
    src = read('gui/app_flet.py')

    # ── 取真相源 ──
    # [EN] ── Take the source of truth ──
    gs = between(src, 'def show_global_settings(self', 'def show_project_settings')
    blk = between(gs, 'tab_defs = [', '\n        ]\n')
    labels = tab_labels(blk)
    REPORT['notes'].append(f'天机页签（{len(labels)} 个）：{labels}')
    # ★★ 2026-11-01：天问新增「花费与优化」（第 3 页，见 `TAB_COST`）⇒ 7 → 8 页。
    #   ⚠ 页数变多的直接后果是**每一页摊到的宽度变小**（`scrollable=False` 之后
    #     Flutter 平分可用宽度）—— 所以"A1 页数"和"A4 装得下"必须一起看：
    #     只改 A1、不看 A4，就等于"页签加进去了，但右边那个又看不见了"。
    # [EN] ★★ 2026-11-01: Tianji gains "Cost & Tuning" (3rd page, see `TAB_COST`) => 7 -> 8.
    # [EN] ⚠ More pages means **less width each** (with `scrollable=False` Flutter splits the
    # [EN] available width evenly) -- so A1 and A4 must be read together: bumping A1 alone would
    # [EN] reproduce "the tab is there but the rightmost one is invisible again".
    ok('A1 ★★ 从源码里取到了**八个**页签（2026-11-01 新增「花费与优化」）',
       len(labels) == 8,
       f'{len(labels)} 个：{labels}')
    # ★★ 2026-10-12：MuMuAINovel 从「AI模型配置」里**拆出来**，成为第 3 个页签
    #   「外部小说服务配置」（用户：「MuMuAINovel还是拆分成一个单独的配置Tab里
    #   就叫做外部小说服务配置」）。
    #   ⚠ 它插在**第 3 位**（紧跟「AI模型配置」），不是排最后 —— 用户说的顺序
    #     就是"拆成单独一个 Tab"，放在原来那一页旁边最顺。
    #     ⚠ 这就意味着 `TAB_GLOBAL_*` 那三个下标**整体后移 1**，见 `app_flet` 那一处。
    # [EN] ★★ 2026-10-12: MuMuAINovel was **split out** of "AI Model Config" into the 3rd tab,
    # [EN] "External Novel Service Configuration".
    # [EN] ⚠ It sits **3rd** (right after "AI Model Config"), not last -- the user's point is "split it into
    # [EN] its own Tab", and next to the page it came from reads most naturally.
    # [EN] ⚠ That means the three `TAB_GLOBAL_*` indices **all shift by 1**; see that spot in `app_flet`.
    # ★ 2026-11-01：「花费与优化」插在**「AI模型配置」右边**（用户选定）——
    #   看完账单顺手换模型。所以前四个是 常规 / AI模型配置 / 花费与优化 / 外部创作服务。
    # [EN] ★ 2026-11-01: "Cost & Tuning" sits **right of "Models & LLM"** (user's choice), so the
    # [EN] first four are General / Models & LLM / Cost & Tuning / External Creative Services.
    ok('A1b ★ 八个名字都在、顺序对（2026-11-01 在「AI模型配置」右边加'
       '「花费与优化」）',
       labels[:4] == ['常规', 'AI模型配置', '花费与优化', '外部创作服务'] and
       labels[4:] == ['界面外观', '运行', '导演与合规', '剧组 Agents'],
       str(labels))

    set_w = num(src, 'SET_W')
    lane_extra = num(src, 'TAB_LANE_EXTRA')
    gutter = num(src, 'TAB_GUTTER')
    ok('A2 ★★ 三个几何常量都读得到（`SET_W` / `TAB_GUTTER` / `TAB_LANE_EXTRA`）',
       min(set_w, lane_extra, gutter) > 0,
       f'SET_W={set_w} GUTTER={gutter} EXTRA={lane_extra}')
    # ★★ 2026-10-12（用户：「天机我也想再放大至少一倍」）：**尺寸改成按窗口算**，
    #   所以这里不再验"常量等于控件+车道+加宽"，改成验**那套算法本身**：
    #     · `tianji_geometry(page)` 是唯一的算法（外框 / 车道 / 栅格三处共用）；
    #     · 它有**下限**（窗口很小也不许比原来窄）；
    #     · 外框真的用了它算出来的数（不是还挂着常量）。
    #   ⚠ 不能再钉 `DLG_W_TABS = SET_W + …`：那个常量现在只是**下限**，
    #     钉住它等于把"按窗口放大"这件事判成失败。
    # [EN] ★★ 2026-10-12 (user: "I want Tianji enlarged at least 2x"): the size is now **computed from
    # [EN] the window**, so this no longer checks "the constant equals controls + lane + widening" but
    # [EN] **the algorithm itself**: `tianji_geometry(page)` is the single algorithm (shared by frame /
    # [EN] lane / grid); it has **lower bounds** (a tiny window must not be narrower than before); and
    # [EN] the frame really uses the numbers it returns.
    # [EN] ⚠ Pinning `DLG_W_TABS = SET_W + ...` is no longer valid: that constant is now only a **lower
    # [EN] bound**, and pinning it would mark "enlarged to the window" as a failure.
    ok('A2b ★★ 天机的几何只有**一处**算法（`tianji_geometry`），外框/车道/栅格共用',
       'def tianji_geometry(page)' in src
       and 'TIANJI_MIN_W = DLG_W_TABS' in src
       and 'TIANJI_MIN_H = DLG_H' in src,
       '')
    # ★★ A2b2 在 2026-10-13 第二轮**改成行为判据**（原来只查 `'w, h = _maximized_size(...)'`
    #   这个字面量，而源码里的变量名是 **`_w, _h`** ⇒ 那条判据**一直红着**，
    #   而它想守的事实其实是好的）。
    #   ⚠ 教训（本项目的纪律）：**"源码里有某个字符串"是弱判据** ——
    #     改个变量名它就红、写在注释里它就绿。改成**真跑一遍**：
    #     给一个"小窗口"和"正常窗口"，断言 `tianji_geometry` 返回的宽高**有下限**。
    # [EN] ★★ A2b2 became a **behavioral** criterion on 2026-10-13 (it used to just look for the literal
    # [EN] `'w, h = _maximized_size(...)'` while the source names the variables **`_w, _h`** ⇒ the
    # [EN] criterion sat permanently red even though the fact it guards was fine).
    # [EN] ⚠ Lesson (this project's discipline): "a string exists in the source" is a weak criterion --
    # [EN] renaming a variable turns it red and putting it in a comment turns it green. So **actually run
    # [EN] it**: give a tiny window and a normal one, and assert `tianji_geometry`'s results have floors.
    _floor_ok = False
    _floor_detail = ''
    try:
        from gui.app_flet import tianji_geometry as _tj, TIANJI_MIN_W as _MINW, \
            TIANJI_MIN_H as _MINH, PAPER_CHROME_W as _PAPERW

        class _FakePage:                                     # 只带 `width` / `height`
            def __init__(self, w, h):
                self.width, self.height = w, h

        _tiny = _tj(_FakePage(10, 10))
        _big = _tj(_FakePage(3840, 2160))
        # ⚠ 三条一起判（缺一个就是一刀切）：
        #   ① 小窗口下**帧宽**与**帧高**不许低于下限；
        #   ② 小窗口下**栅格** = 帧宽 − `PAPER_CHROME_W`（paper_frame 自己在帧内吃掉的）
        #      —— ⚠ **栅格天生比帧窄 54px**，第一版我误把它也要求 ≥ `MINW`，
        #        于是"产品明明对、判据说错"（850 vs 904）。
        #   ③ 大窗口下**三项都不小于**小窗口（"窗口大了，界面跟着大"这件事真的成立）。
        # [EN] Three assertions together: ① at a tiny window the frame's width/height must not fall
        # [EN] below the floors; ② the grid is frame - `PAPER_CHROME_W` (⚠ the grid is inherently 54px
        # [EN] narrower -- the first version wrongly required it to be >= MINW too, a false red at
        # [EN] 850 vs 904); ③ at a large window all three are >= the tiny ones.
        _floor_ok = (isinstance(_tiny[0], (int, float)) and _tiny[0] >= _MINW
                     and isinstance(_tiny[1], (int, float)) and _tiny[1] >= _MINH
                     and isinstance(_tiny[2], (int, float))
                     and abs(_tiny[2] - max(set_w, _tiny[0] - _PAPERW)) <= 2
                     and _big[0] >= _tiny[0] and _big[1] >= _tiny[1] and _big[2] >= _tiny[2])
        _floor_detail = (f'小窗口(10×10)={_tiny} / 大窗口(3840×2160)={_big} / '
                         f'下限={_MINW}×{_MINH} / 栅格应=帧−{_PAPERW}')
    except Exception as _ex:                                 # noqa: BLE001
        _floor_detail = f'跑不起来：{_ex!r}'
    ok('A2b2 ★★ 算法里**有下限**（窗口是 0/很小的时候不许比原来还窄）'
       '—— 真跑一遍小窗口与大窗口，量出来的',
       _floor_ok, _floor_detail)
    dlg = set_w + gutter + lane_extra
    ok('A2c ★★ 天机对话框**真的用了算出来的宽度**（不是还挂着固定常量）',
       'ft.Container(content=tabs, width=_tj_w, height=_tj_h)' in gs
       and '_tj_w, _tj_h, _tj_grid = tianji_geometry(page)' in gs,
       '')

    # ── 宽度够不够（用真实字体量）──
    # ⚠ 必须在**天机那个 TabBar 的实参块里**找：`label_padding=ft.Padding(12, …)`
    #   在帮助面板里也有一份（而且出现得更早）—— 全文搜会把那一份当成天机的，
    #   于是把天机那份删掉判据也不红（第一版就是这么漏的）。
    # [EN] ── Is the width enough (measured with the real font) ──
    # [EN] ⚠ Must be found in **the args block of the Tianji TabBar**: `label_padding=ft.Padding(12, ...)`
    # [EN] There is also one in the help panel (and it appears earlier) — a full-text search will treat
    # [EN] that one as Tianji's,
    # [EN] so even if Tianji's is deleted the assertion won't go red (the first version missed it this
    # [EN] way).
    tb_args = between(gs, 'ft.TabBar(', 'ft.TabBarView(')
    pad = int((re.search(r'label_padding=ft\.Padding\((\d+),', tb_args)
               or [0, 0])[1] or 0)
    ok('A3 ★★ 天机页签给了显式的 `label_padding`（不给就走 Flutter 默认的'
       '16 每侧，宽度算不准）—— 在**天机那个 TabBar 的实参块里**查',
       pad > 0, f'每侧 {pad}px')
    m = measure(labels, 14, pad)
    REPORT['measure'] = m
    # 顺带把**旧设置**量一遍记进报告：旧代码没给 `label_padding`，
    # 走的是 Flutter 默认 16 每侧；而那时宽度只有 `DLG_W`=600。
    # 这一条**不做断言**（PIL 的字宽只是 Flutter 排版的近似，用它去复现
    # "当时确实装不下"这件事本身就不可靠），只把数字留下来给后来的人看：
    # 用户报的"右边少一个页签"是实机现象，而这里两边的数差距只有几个像素 ——
    # 所以真正的修法**不是**"把宽度调大一点点"，而是关掉 `scrollable`（A5）。
    # [EN] Also measure the **old settings** and record them in the report: the old code didn't provide
    # [EN] `label_padding`,
    # [EN] so it used Flutter's default 16 per side; and back then the width was only `DLG_W`=600.
    # [EN] This item **makes no assertion** (PIL's text width is only an approximation of Flutter's layout,
    # [EN] and using it to reproduce
    # [EN] "it really didn't fit back then" is itself unreliable), just leave the numbers for later
    # [EN] readers:
    # [EN] what the user reported, "the right side is missing a tab", is a real-device phenomenon, whereas
    # [EN] here the difference between the two sides is only a few pixels —
    # [EN] so the real fix is **not** "make the width a bit larger", but turning off `scrollable` (A5).
    old = measure(labels, 14, 16)
    REPORT['notes'].append(
        f'旧设置量一遍（无 label_padding、宽度 600）：需要 {old["需要宽度"]} —— '
        f'与当时的可用宽度只差几个像素，靠"加宽一点"治不了根，'
        f'所以这一支的重心是 A5 的 `scrollable=False`。')
    ok(f'A4 ★★★ **八个页签真的装得下**（按**下限**宽度算 —— 实际更宽，只会更宽裕）：'
       f'需要 {m["需要宽度"]} ≤ 可用 {dlg} − 余量 {MARGIN}'
       f'（余量 {dlg - m["需要宽度"]:.0f}px）—— 这就是"所有 Tab 都看得见"的判据',
       m['需要宽度'] <= dlg - MARGIN,
       str(m['明细']))

    # ── scrollable 必须显式关掉 ──
    # [EN] ── scrollable must be explicitly turned off ──
    tb = between(gs, 'ft.TabBar(', 'ft.TabBarView(')
    ok('A5 ★★★ 天机页签 **`scrollable=False`** —— Flet 1.0 默认 `True`，'
       '装不下的页签会被推到可视区**外面**（静默消失，用户报的就是这个）。'
       '关掉之后"装不下"会表现为字被压窄，那是看得见的',
       'scrollable=False' in tb, tb[:200].replace('\n', ' '))

    # ── 车道跟着加宽（否则右边空一大片纸）──
    # [EN] ── widen the lane accordingly (otherwise a large blank sheet on the right) ──
    # ★ 2026-10-12：车道改成**显式宽度**（`lane_w`），不再是"控件 520 + 留白"。
    #   验两点：① 车道 = 栅格 + TAB_GUTTER（这样滚动条才落在右边缘）；
    #          ② 对齐是**左对齐**（用户：「所有配置记得左对齐」）。
    # [EN] ★ 2026-10-12: the lane takes an **explicit width** (`lane_w`), no longer "controls at 520 +
    # [EN] padding". Two things are checked: (1) lane = grid + TAB_GUTTER (so the scrollbar lands on the
    # [EN] right edge); (2) alignment is **left** (user: "remember to left-align all settings").
    # ⚠⚠ 2026-10-23：那条页签改成"自己带布局"（`_wrap_tab_content` 认出
    #   `_tab_ready` 就直接返回），于是天机这里的写法从
    #   `mk_tab_content(c, lane_w=_tj_grid + TAB_GUTTER)` 变成了
    #   `_wrap_tab_content(c, _tj_grid + TAB_GUTTER)` —— 宽度**还是一样算的**，
    #   只是从关键字参数变成了位置参数。老锚点必然红。
    #   ⇒ 判据改成"宽度仍然由 `栅格 + TAB_GUTTER` 决定"，两种写法都认；
    #     再加一条：**没有任何一页**把 lane 写成固定数字（那样滚动条会压到内容上）。
    # [EN] ⚠⚠ 2026-10-23: that page became "bring your own layout" (`_wrap_tab_content`
    # returns it as-is when `_tab_ready`), so the call changed from
    # `mk_tab_content(c, lane_w=_tj_grid + TAB_GUTTER)` to
    # `_wrap_tab_content(c, _tj_grid + TAB_GUTTER)` -- **the width is computed identically**,
    # only keyword-to-positional. The old anchor necessarily goes red.
    # => Judge "the width is still `grid + TAB_GUTTER`", accepting both forms; plus: **no
    # page** hard-codes the lane to a number (that puts the scrollbar on top of content).
    ok('A6 ★★ 天机的车道宽度 = 栅格 + TAB_GUTTER（滚动条才落在右边缘）',
       ('lane_w=_tj_grid + TAB_GUTTER' in gs
        or '_wrap_tab_content(c, _tj_grid + TAB_GUTTER)' in gs),
       '')
    ok('A6c ★★ 没有任何一页把车道宽度**写死成数字**（写死的话滚动条会压在内容上）',
       'lane_w=_tj_grid + 0' not in gs
       and 'lane_w=SET_W' not in gs,
       '')
    ok('A7 ★★★ 天机的控件是**左对齐**的（用户：「所有配置记得左对齐」）',
       'align=ft.CrossAxisAlignment.START' in gs, '')
    ok('A6b ★ 而 `mk_tab_content` **确实支持** `lane_extra`（写了不认，等于没写）',
       'def mk_tab_content(controls: list, pane_h: int = None,\n'
       '                   lane_extra: int = 0)' in src
       or 'lane_extra: int = 0' in src, '')

    # ── 每个页签都挂了悬停解释（用户同日要求的 Tip）──
    # [EN] ── every tab has a hover tooltip attached (a Tip the user requested the same day) ──
    tips = re.findall(r"(?m)^ {12}\(t\(\"[^\"]+\"\),[^\n]*", blk)
    n_tips = len(re.findall(r'tooltip=TAB_TIPS\[i\]', gs))
    ok('A7 ★★ 每个页签都挂上了悬停解释（`tooltip=TAB_TIPS[i]`）—— '
       '页面里配了 `TAB_TIPS` 却不挂到 `ft.Tab` 上，等于没写',
       n_tips == 1 and 'TAB_TIPS' in gs, f'tooltip 挂接 {n_tips} 处')
    ok('A7b ★★ `TAB_TIPS` 的条数与页签数**对得上**（配少一条会在建界面时'
       '当场 assert 炸掉 —— 与其线上炸，不如现在就说）',
       'assert len(TAB_TIPS) == len(tab_defs)' in gs, '')


def test_book_tabs() -> None:
    """书斋是同一套控件、同一个坑（旧代码没关 `scrollable`）。
        English:
    Shuzhai is the same set of controls and the same pitfall (the old code didn't turn off
    `scrollable`).
    """
    src = read('gui/app_flet.py')
    ps = between(src, 'def show_project_settings', 'def _close_dlg')
    tb = between(ps, 'ft.TabBar(', 'ft.TabBarView(')
    ok('B1 ★★ 书斋的页签也 **`scrollable=False`** —— 同一个坑，'
       '只堵天机那一个不算修好（书的页签以后还会加）',
       'scrollable=False' in tb, tb[:160].replace('\n', ' '))
    ok('B2 ★ 书斋每个页签也挂了悬停解释（`tooltip=BOOK_TIPS[i]`）'
       '—— 顺便把"书斋 vs 天机"这件事在每个页签上说穿',
       'tooltip=BOOK_TIPS[i]' in ps, '')
    ok('B2b ★ `BOOK_TIPS` 条数与页签数对得上',
       'assert len(BOOK_TIPS) == len(tab_defs)' in ps, '')

    help_src = between(src, "def show_help_dialog", 'def _scroll_bar')
    ok('B3 ★ 帮助面板的两个页签也 `scrollable=False`（同一类坑）',
       'scrollable=False' in between(help_src, 'ft.TabBar(', 'ft.TabBarView('),
       '')

    # ★ 2026-10-13 修的"两个页签挤在左上角"：`scrollable=False` 只是让 Flet 默认
    #   `tab_alignment=FILL`，但 `TabBar` 必须**被父列撑开**才铺得满——父 `Column`
    #   默认 `START`，所以必须显式 `STRETCH`。这条守的是 STRETCH，丢了它两个
    #   页签就退回贴左（用户报的"帮助信息的 2 个 tab 都靠左对齐"）。
    #   ⚠ 提取块用 `ft.TabBarView(` … `expand=True,\n        )`（帮助对话框里**唯一**
    #   的 Tabs 收尾），正好把 `TabBarView` 之后那行 `STRETCH` 包进来；帮助函数里
    #   `ft.TabBarView(` 与这个收尾都只出现一次，边界干净、不会误中别的 STRETCH。
    # [EN] ★ 2026-10-13 fix for "the two tabs huddle in the top-left corner": `scrollable=False`
    # [EN] only makes Flet default `tab_alignment=FILL`, but the TabBar must be **stretched by its
    # [EN] parent column** to fill the row -- the parent `Column` defaults to `START`, so an explicit
    # [EN] `STRETCH` is required. This check guards STRETCH; without it the two tabs hug the left
    # [EN] again (the user's report "the help dialog's 2 tabs are all left-aligned").
    # [EN] ⚠ the extraction block uses `ft.TabBarView(` through the Tabs closing `expand=True,\n        )`
    # [EN] (the **only** such closing in the help dialog), which wraps the `STRETCH` line that comes
    # [EN] after `TabBarView`; both appear exactly once in the help function, so the boundary is clean
    # [EN] and won't accidentally match some other STRETCH.
    help_tabs_block = between(help_src, 'ft.TabBarView(', 'expand=True,\n        )')
    ok('B3b ★★ 帮助面板的两个页签**撑满整行**（`Column` 显式 '
       '`horizontal_alignment=ft.CrossAxisAlignment.STRETCH`，否则挤在左上角）',
       'horizontal_alignment=ft.CrossAxisAlignment.STRETCH' in help_tabs_block,
       help_tabs_block[:200].replace('\n', ' '))


def test_scanner() -> None:
    """这一支全靠"从源码里取到的块"，必须证明取到的块不是空的、也不是全域。
        English:
    This branch relies entirely on "blocks extracted from the source", and must prove the extracted
    blocks are neither empty nor global.
    """
    src = read('gui/app_flet.py')
    gs = between(src, 'def show_global_settings(self', 'def show_project_settings')
    ok('D1 ★★ `between()` 取到的是**天机那一段**，不是整份文件'
       '（否则 `scrollable=False` 会被书斋/帮助那两处骗过去）',
       2000 < len(gs) < len(src) // 2, f'{len(gs)} 字符 / 全文 {len(src)}')
    ok('D1b ★★ 而且取到的那一段里**没有**书斋才有的东西（范围没串）',
       'def show_project_settings' not in gs, '')


def main() -> int:
    for name, fn in (('天机页签', test_global_tabs), ('书斋与帮助', test_book_tabs),
                     ('扫描器自检', test_scanner)):
        try:
            fn()
        except Exception:                                       # noqa: BLE001
            REPORT['checks'].append({'name': f'{name} 组崩了', 'ok': False,
                                     'detail': traceback.format_exc()[-900:]})
    out = APP / 'assets' / 'screenshots' / 'tabs_fit_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')

    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n页签宽度验证：{n - len(bad)}/{n}')
    for c in REPORT['checks']:
        print(f'  {"✓" if c["ok"] else "✗"} {c["name"]}'
              + (f' | {c["detail"][:140]}' if c['detail'] else ''))
    for x in REPORT['notes']:
        print('  · ', x)
    print('报告 ->', out.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
