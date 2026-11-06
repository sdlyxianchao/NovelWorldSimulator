# -*- coding: utf-8 -*-
"""真机验证：用量报表的**栏头筛选菜单**（2026-10-11）。

用户原话
--------
「关于用量 界面设计有问题，你现在最上面那几个筛选功能，希望是除了最左边列，
中间第二个第三个列都有自己的一套筛选，且用合适的**上下文菜单**的方式放到**每个列的表头上**，
而不是单独放一个地方。」

于是顶上那排「划分 / 自」两个下拉**被拆掉**，改成：

    · 第 2 栏栏头 → 「划分方式」菜单（软件整体 3 项 / 项目 4 项，跟着 scope 变）
    · 第 3 栏栏头 → 「时间范围」+「Agent 筛选」两个菜单（用户选了"两套都放第 3 栏"）
    · 第 1 / 第 4 栏栏头只有标题（用户点名"除了最左边列"；第 4 栏明细表**不加**）
    · 栏头在**滚动区之外** —— 内容滚起来，筛选还钉在顶上

为什么必须真机
--------------
「菜单画出来了没有」「点菜单真的改变了内容吗」—— 这两件事**读源码和读控件树都答不了**
（本项目的老账：控件树里对 ≠ 屏幕上看得见）。所以分三层：

    A 结构：四栏 + 四个栏头 · 顶上不再有那两个下拉 · **3 个菜单都在某个栏头里**
    B 行为：点菜单项 → 状态真的变、第 1/2/3 栏的内容真的跟着变（含**对照**）
    C 像素：把三个菜单按钮涂成品红 → 数像素、看位置（**只动颜色不动几何**）

跑法：`.venv\\Scripts\\python.exe tools\\verify_usage_filters.py`
产出：`assets/screenshots/usage_filters.png` + `usage_filters_report.json`

⚠ 用**夹具库**（临时 `usage.db` + 中性的项目名/模型名）：绝不碰用户真实的 `usage.db`，
  也不把真实项目名拍进图里（`verify_generic_project` 盯着这件事）。
⚠ 收尾三件套：写报告 → `await shutdown(page, code=…)`。
  **别写在 `ft.run()` 之后** —— 那是死代码（`ft.run` 阻塞到窗口关闭才返回）。

English:
Real-machine verification: the **header filter menu** of the usage report (2026-10-11).
User's exact words
--------
"There's a design problem with the usage UI. The filter controls you currently have at the top —
I'd like, apart from the leftmost column,
the middle second and third columns to each have their own set of filters, placed as appropriate
**context menus** on **each column's header**,
rather than in a single separate place."
So the two dropdowns "division / self" at the top **were removed**, replaced with:
    · Column 2 header → "Division method" menu (3 items for the whole app / 4 items for project, changing with scope)
    · Column 3 header → "Time range" + "Agent filter" two menus (user chose "put both in column 3")
    · Column 1 / Column 4 headers have only a title (user specified "apart from the leftmost column"; column 4 detail table gets **nothing**)
    · Headers are **outside the scroll area** — content scrolls, filters stay pinned at the top
Why real-machine is required
--------------
"Is the menu drawn" "does clicking the menu really change the content" — these two things
**cannot be answered by reading source code or reading the control tree**
(this project's old debt: the control tree being right ≠ it being visible on screen). So three
layers:
    A Structure: four columns + four headers · no more of those two dropdowns at the top · **all 3 menus are inside some header**
    B Behavior: click a menu item → state really changes, column 1/2/3 content really changes with it (including **controls**)
    C Pixels: paint the three menu buttons magenta → count pixels, check positions (**only change color, not geometry**)
How to run: `.venv\\Scripts\\python.exe tools\\verify_usage_filters.py`
Output: `assets/screenshots/usage_filters.png` + `usage_filters_report.json`
⚠ Use the **fixture DB** (temporary `usage.db` + neutral project names/model names): never touch
the user's real `usage.db`,
  and never photograph real project names into the image (`verify_generic_project` watches over this).
⚠ The cleanup trio: write the report → `await shutdown(page, code=…)`.
  **Do not write it after `ft.run()`** — that is dead code (`ft.run` blocks until the window closes before returning).
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import flet as ft                                     # noqa: E402
from PIL import Image                                 # noqa: E402

import verify_ui_common as VU                         # noqa: E402
from util.flet_shutdown import shutdown               # noqa: E402

from config import CFG                                # noqa: E402
CFG.set('MOCK_LLM', 'true')                           # 零成本、零网络、可复现
# [EN] Zero cost, zero network, reproducible
CFG.set('LANGUAGE', 'zh')

VU.redirect_env_writes()                              # 起界面的脚本一律禁写真实 .env
# [EN] Scripts that launch the UI are strictly forbidden from writing the real .env

from gui.app_flet import NovelWorldApp                # noqa: E402
from gui.usage_dialog import SINCE_PRESETS, _preset_since   # noqa: E402
from i18n import set_lang                             # noqa: E402
set_lang('zh')

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}

#: 标记色（全项目没人用）—— 用于"菜单按钮真的画出来了吗"这条像素判据。
# [EN] : marker color (nobody in the whole project uses it) — used for the pixel criterion "did the
# [EN] menu buttons actually get drawn".
MARK = '#ff00ff'

#: 夹具：三笔"今天"+ 一笔**30 天前**（用来验"时间范围"是真的在起作用）。
#: 名字一律中性（不放用户的书名/模型名进截图）。
# [EN] : fixture: three entries for "today" + one entry **30 days ago** (used to verify that "time
# [EN] range" is really taking effect).
# [EN] : names are always neutral (do not put the user's book titles/model names into screenshots).
SEED = [
    # (项目, 模型, 用途, Agent, 入, 出, 花费, 几天前)
    # [EN] (project, model, purpose, Agent, input, output, cost, days ago)
    ('甲项目', 'model-a', 'crew_novelist', '小说作家', 12000, 3400, 0.20, 0),
    ('甲项目', 'model-b', 'crew_screen', '剧作者', 8000, 2200, 0.03, 0),
    ('甲项目', 'model-b', 'book_scan', '', 400, 120, 0.004, 0),
    ('甲项目', 'model-old', 'book_scan', '', 9000, 900, 0.50, 30),
    ('乙项目', 'model-a', 'crew_review', '复盘', 5000, 1200, 0.02, 0),
]


def ok(name: str, cond: bool, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'\n        {str(detail)[:200]}' if (detail and not cond) else ''))
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  控件树小工具（都在"这一支判据"里用，不往 verify_ui_common 里塞）
# [EN] Control-tree helpers (all used within "this criterion branch", don't stuff them into
# [EN] verify_ui_common)
# ══════════════════════════════════════════════════════════════════
def _by_attr(dlg, attr: str) -> dict:
    """树里带某个抓手属性的控件 → {值: 控件}。
        English:
    Controls in the tree with a certain handle attribute → {value: control}.
    """
    out: dict = {}
    for c in VU.walk(dlg):
        v = getattr(c, attr, None)
        if v:
            out[v] = c
    return out


def _panes(dlg) -> dict:
    return {int(k): v for k, v in _by_attr(dlg, '_usage_pane').items()}


def _menus(dlg) -> dict:
    return _by_attr(dlg, '_usage_menu')


def _click_menu_item(btn, text: str) -> bool:
    """点一个菜单里文字含 `text` 的那一项（走它自己的 `on_click`）。
        English:
    Click the item in a menu whose text contains `text` (go through its own `on_click`).
    """
    for it in (getattr(btn, 'items', None) or []):
        c = getattr(it, 'content', None)
        if isinstance(c, ft.Text) and text in str(c.value or ''):
            fn = getattr(it, 'on_click', None)
            if fn is None:
                return False
            fn(None)
            return True
    return False


def _click_box(dlg, text: str) -> bool:
    """点树里那个"可点、且子树里写着 `text`"的容器（左栏行 / 卡片都是这个形状）。
        English:
    Click the container in the tree that is "clickable and has `text` in its subtree" (left column
    rows / cards are all this shape).
    """
    for c in VU.walk(dlg):
        if getattr(c, 'on_click', None) is None:
            continue
        if not isinstance(getattr(c, 'content', None), ft.Column):
            continue
        if any(str(x) == text for x in VU.all_texts(c)):
            c.on_click(None)
            return True
    return False


def _col_texts(dlg, pane_no: int) -> list:
    return VU.all_texts(_panes(dlg)[pane_no])


def _count_of(text: str) -> int:
    """从「5 次 · ¥0.75」里取出那个 5（取不到 -1）。

    ★ 判据**别把笔数写死**：夹具加一笔就得改判据，而"改了夹具忘改判据"
      正是假红最常见的来源（这一支第一版就写死了 4，而夹具是 5 笔）。
      改成"最近 7 天 == 全部 - 1"这种**关系式**，夹具怎么变都成立。
    
        English:
    Extract the 5 from "5 times · ¥0.75" (return -1 if not found).
        ★ Criterion: **do not hardcode the entry count**: adding one entry to the fixture would require changing the criterion, and "changed the fixture but forgot to change the criterion"
          is exactly the most common source of false red (this branch's first version hardcoded 4, but the fixture has 5 entries).
          Change it to a **relational expression** like "last 7 days == all - 1", which holds no matter how the fixture changes.
    """
    m = re.match(r'\s*(\d+)\s*次', str(text or ''))
    return int(m.group(1)) if m else -1


def _scope_count_text(dlg) -> str:
    """第 1 栏「软件整体」那一行下面的小字（形如「4 次 · ¥0.75」）。

    ★ 这是"时间范围真的作用到四栏"的**观测量**：它在第 1 栏（不是第 3 栏），
      却会随着第 3 栏那个菜单变 —— 正好证明"时间范围是全局窗口"。
    
        English:
    The small text under the column 1 "whole app" row (of the form "4 times · ¥0.75").
        ★ This is the **observable** for "time range really applies to all four columns": it is in column 1 (not column 3),
          yet it changes with the menu in column 3 — exactly proving that "time range is a global window".
    """
    ts = _col_texts(dlg, 1)
    for i, x in enumerate(ts):
        if str(x).strip() == '软件整体' and i + 1 < len(ts):
            return str(ts[i + 1])
    return ''


def _paint(btn, color: str = MARK) -> list:
    """把一个菜单按钮涂成标记色，返回**原来的颜色**（供还原）。

    ★ 「只动颜色、不动几何」—— 量到的就是它真实的位置。
    ⚠ 颜色的取值要**记下来再还原**：这一支曾经直接写 `color=None`，
      于是那张"给人看"的截图里菜单是主题默认色（不是界面本来的色）。
    
        English:
    Paint a menu button with the marker color, return **the original color** (for restoration).
        ★ "Only change color, not geometry" — what is measured is its real position.
        ⚠ The color values must be **recorded and then restored**: this branch once directly wrote `color=None`,
          so in that "human-facing" screenshot the menu was the theme default color (not the UI's original color).
    """
    saved: list = []
    for obj, attr in ((btn, 'icon_color'),):
        try:
            saved.append((obj, attr, getattr(obj, attr, None)))
            setattr(obj, attr, color)
        except Exception:                                # noqa: BLE001
            pass
    for x in VU.walk(btn):
        if isinstance(x, (ft.Text, ft.Icon)):
            try:
                saved.append((x, 'color', getattr(x, 'color', None)))
                x.color = color
            except Exception:                            # noqa: BLE001
                pass
    return saved


def _unpaint(saved: list) -> None:
    for obj, attr, old in saved:
        try:
            setattr(obj, attr, old)
        except Exception:                                # noqa: BLE001
            pass


def _mark_pixels(raw: bytes) -> tuple:
    """截图里标记色的像素数 + y/x 分布（半透明界面上按"红蓝都高、绿明显低"判）。
        English:
    Pixel count of the marker color in the screenshot + y/x distribution (on the semi-transparent
    UI, judged by "both red and blue high, green clearly low").
    """
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    w, h = im.size
    buf = im.tobytes()                     # ⚠ 别用 getdata()：Pillow 已标它要移除
    # [EN] ⚠ Do not use getdata(): Pillow has marked it for removal
    ys, xs = [], []
    for i in range(0, len(buf), 3):
        r, g, b = buf[i], buf[i + 1], buf[i + 2]
        if r > 190 and b > 190 and g < 110:
            n = i // 3
            ys.append(n // w)
            xs.append(n % w)
    return len(ys), ys, xs, (w, h)


# ══════════════════════════════════════════════════════════════════
async def _body(page, tmp: Path) -> None:
    import llm.usage as U

    VU.isolate_projects_dir(tmp / 'Projects')
    db = tmp / 'usage.db'
    U.db_path = lambda: db                              # 打桩：所有读写都落在夹具库
    # [EN] Stubbing: all reads and writes land in the fixture DB
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

    app.show_usage_dialog()
    await asyncio.sleep(1.5)
    dlg = None
    for d in reversed(VU.open_dialogs(page)):
        if isinstance(d, ft.AlertDialog):
            dlg = d
    if not ok('A1 用量对话框真的打开了', dlg is not None, '没找到开着的 AlertDialog'):
        return
    st = getattr(dlg, '_usage_state', None)
    if not ok('A1b 对话框把状态挂出来了（`_usage_state`，判据的抓手）',
              isinstance(st, dict), type(st).__name__):
        return

    panes, menus = _panes(dlg), _menus(dlg)

    def M(tag: str):
        """**每次都重新取**当前树上的那个菜单。

        ⚠ 不能把 `_menus(dlg)` 的结果一直拿着用：`build_heads()` 每刷一次
          **会新建**按钮对象（`head2.content = _head(...)`），老对象就不在树上了 ——
          点它虽然还能改状态（回调是闭包），但**涂色量像素会量到 0**（屏幕上没它）。
          这一支第一版就是这么栽的。
        
                English:
        **Re-fetch** that menu from the current tree every time.
                ⚠ Do not keep using the result of `_menus(dlg)`: every time `build_heads()` refreshes,
                  it **creates new** button objects (`head2.content = _head(...)`), and the old object is no longer in the tree --
                  clicking it can still change state (the callback is a closure), but the **colored pixel count will measure 0** (it's not on screen).
                  This was exactly how the first version of this branch failed.
        """
        return _menus(dlg).get(tag)

    # ── A 结构 ──────────────────────────────────────────────────
    # [EN] ── A Structure ──────────────────────────────────────────────────
    ok('A2 四栏都在（抓手 `_usage_pane` 1..4）', sorted(panes) == [1, 2, 3, 4],
       f'找到 {sorted(panes)}')
    heads: dict = {}
    for n, p in panes.items():
        box = getattr(p, 'content', None)
        kids = list(getattr(box, 'controls', None) or [])
        heads[n] = kids[0] if kids else None
    ok('A3 四栏各有栏头（每栏第一个子控件）', all(heads.values()),
       f'缺 {[n for n in (1, 2, 3, 4) if not heads.get(n)]}')
    ok('A4 栏头是"栏头 + 内容"两层（内容在**滚动区**里、栏头在外）',
       all(len(list(getattr(getattr(panes[n], 'content', None), 'controls', []) or [])) == 3
           for n in (1, 2, 3, 4))
       and all(getattr(list(getattr(panes[n].content, 'controls'))[2], 'scroll', None)
               is not None for n in (1, 2, 3, 4)),
       '栏头没在滚动区之外，或者内容不可滚动')
    allt = [str(x) for x in VU.all_texts(dlg)]
    ok('A5 四个栏头的标题都在（范围 / 划分 / Agent / 明细）',
       all(any(x.strip() == k for x in allt) for k in ('范围', '划分', 'Agent', '明细')),
       [k for k in ('范围', '划分', 'Agent', '明细')
        if not any(x.strip() == k for x in allt)])

    drops = [c for c in VU.walk(dlg) if isinstance(c, (ft.DropdownM2, ft.Dropdown))]
    ok('A6 ★★ 顶上那排筛选**已经拆掉**（对话框里只剩 1 个下拉 = 导出语言）',
       len(drops) == 1,
       f'还有 {len(drops)} 个下拉 —— 用户要的是"而不是单独放一个地方"')

    ok('A7 ★★★ 三个菜单都在（划分 / 时间范围 / Agent 筛选）',
       sorted(menus) == ['agent', 'by', 'since'], f'找到 {sorted(menus)}')

    where: dict = {}
    for tag, btn in menus.items():
        for n, head in heads.items():
            if head is not None and any(x is btn for x in VU.walk(head)):
                where[tag] = n
    ok('A8 ★★★ 划分菜单在**第 2 栏的栏头**里', where.get('by') == 2, where)
    ok('A9 ★★★ 时间范围 + Agent 筛选两个菜单都挂在**第 3 栏的栏头**里'
       '（用户选的是"两套都放第 3 栏"）',
       where.get('since') == 3 and where.get('agent') == 3, where)
    ok('A10 ★★ 第 1 / 第 4 栏的栏头里**没有**任何筛选菜单'
       '（用户："除了最左边列"；第 4 栏明细表不加）',
       not any(n in (1, 4) for n in where.values()), where)

    # 菜单里"当前项带勾" —— 这是从下拉框换成菜单时最容易丢掉的信息
    # [EN] "current item has a check" in the menu — this is the info most easily lost when switching from a
    # [EN] dropdown to a menu
    checked = {}
    for tag, btn in _menus(dlg).items():
        checked[tag] = [str(getattr(getattr(it, 'content', None), 'value', ''))
                        for it in (getattr(btn, 'items', None) or [])
                        if getattr(it, 'checked', False)]
    ok('A11 ★★ 菜单里**当前那一项带勾**（"现在是哪个筛选"读得出来）',
       all(len(v) == 1 for v in checked.values()), checked)

    # ── B 行为 ──────────────────────────────────────────────────
    # [EN] ── B Behavior ──────────────────────────────────────────────────
    before = str(st['by'])
    hit = _click_menu_item(M('by'), '日期')
    page.update()
    await asyncio.sleep(0.6)
    ok('B1 ★★★ 点划分菜单的「日期」→ 状态真的变了',
       hit and st['by'] == '日期' and before != st['by'],
       f"{before} -> {st['by']} (clicked={hit})")
    texts2 = _col_texts(dlg, 2)
    ok('B1b 第 2 栏真的按新划分重画了（卡片标题变成日期）',
       any(str(x).startswith(('20', '19')) for x in texts2), texts2[:6])
    #  ⚠ 文案在 `ft.Text.value` 上（`content` 是 None）—— 第一版去读 `.content.value`，
    #    于是**明明已经是「日期」也判红**（判据的错，不是产品的错）。
    # [EN] ⚠ The text is on `ft.Text.value` (`content` is None) — the first version read `.content.value`,
    # [EN] so **it flagged red even when it was already "date"** (a criterion bug, not a product bug).
    ok('B1c 第 2 栏栏头的按钮文字跟着改（"模型" → "日期"）',
       any(str(x).strip() == '日期' for x in VU.all_texts(heads[2])),
       VU.all_texts(heads[2]))

    cnt_all = _scope_count_text(dlg)
    _click_menu_item(M('since'), '最近 7 天')
    page.update()
    await asyncio.sleep(0.8)
    ok('B2 ★★ 点时间范围「最近 7 天」→ 状态是算法算出来的那个日期',
       st['since'] == _preset_since(7), f"since={st['since']!r}")
    cnt_7 = _scope_count_text(dlg)
    ok('B3 ★★★ 时间范围**真的作用到四栏**（第 1 栏「软件整体」的次数少掉那笔 30 天前的）',
       _count_of(cnt_all) > 0 and _count_of(cnt_7) == _count_of(cnt_all) - 1,
       f'全部={cnt_all!r} 最近7天={cnt_7!r}')
    _click_menu_item(M('since'), '全部时间')
    page.update()
    await asyncio.sleep(0.8)
    ok('B4 ★★ 点回「全部时间」→ 那笔 30 天前的账回来了（对照组）',
       st['since'] == '' and _count_of(_scope_count_text(dlg)) == _count_of(cnt_all),
       f"since={st['since']!r} n={_scope_count_text(dlg)!r} 基线={cnt_all!r}")

    # 第 3 栏自己那套筛选（要先把 scope 和卡片选起来）
    # [EN] Column 3's own filtering (need to select scope and card first)
    _click_box(dlg, '甲项目')
    page.update()
    await asyncio.sleep(0.8)
    _click_menu_item(M('by'), '模型')
    page.update()
    await asyncio.sleep(0.6)
    opened = _click_box(dlg, 'model-b')
    page.update()
    await asyncio.sleep(0.8)
    agents0 = [str(x) for x in _col_texts(dlg, 3)]
    ok('B5 选中一张卡片后第 3 栏有 Agent 明细（含"（未标：…）"那一档）',
       opened and any('未标' in x for x in agents0) and len(agents0) >= 3, agents0)

    clicked = _click_menu_item(M('agent'), '只看剧组 Agent')
    page.update()
    await asyncio.sleep(0.8)
    agents1 = [str(x) for x in _col_texts(dlg, 3)]
    ok('B6 ★★★ Agent 筛选「只看剧组 Agent」→ 第 3 栏不再出现"（未标：…）"',
       clicked and st['agent_kind'] == 'crew' and not any('未标' in x for x in agents1)
       and any('剧作者' in x for x in agents1), f'{st["agent_kind"]} {agents1}')

    # 顺手留一张"筛选真生效"的图（第 3 栏只剩剧组 Agent）—— 给人看，也给下次改这一窗时当底片
    # [EN] Also grab a screenshot of "filtering really works" (column 3 has only the crew Agent left) — for
    # [EN] humans, and as a baseline next time this window is changed
    raw = await page.take_screenshot()
    if raw:
        (OUT / 'usage_filters_crew.png').write_bytes(raw)
        ok('D2 「只看剧组 Agent」生效时的截图落盘', (OUT / 'usage_filters_crew.png').is_file())

    _click_menu_item(M('agent'), '只看未标用途')
    page.update()
    await asyncio.sleep(0.8)
    agents2 = [str(x) for x in _col_texts(dlg, 3)]
    ok('B7 ★★★ Agent 筛选「只看未标用途」→ 只剩那一档',
       st['agent_kind'] == 'unknown' and any('未标' in x for x in agents2)
       and not any('剧作者' in x for x in agents2), agents2)

    _click_menu_item(M('agent'), '只看花费较大的')
    page.update()
    await asyncio.sleep(0.8)
    agents3 = [str(x) for x in _col_texts(dlg, 3)]
    ok('B8 ★★ 门槛筛选「只看花费较大的」→ 这一栏的账全都小于门槛 ⇒ 出空态文案'
       '（一片空白看着像坏了）',
       st['agent_kind'] == 'major' and any('没有明细' in x for x in agents3), agents3)

    _click_menu_item(M('agent'), '全部 Agent')
    page.update()
    await asyncio.sleep(0.8)
    agents4 = [str(x) for x in _col_texts(dlg, 3)]
    ok('B9 ★★ 点回「全部 Agent」→ 两档都回来了（对照组）',
       st['agent_kind'] == 'all' and any('未标' in x for x in agents4)
       and any('剧作者' in x for x in agents4), agents4)

    # ── C 像素：菜单按钮真的画出来了吗 ──────────────────────────
    # [EN] ── C Pixels: did the menu buttons actually get drawn ──────────────────────────
    saved: list = []
    for btn in _menus(dlg).values():                     # ⚠ 取**当前树上**的那三个
    # [EN] ⚠ Grab the three **on the current tree**
        saved += _paint(btn)
    page.update()
    await asyncio.sleep(0.6)
    raw = await page.take_screenshot()
    n_mark, ys, xs, (w, h) = (0, [], [], (0, 0))
    if raw:
        n_mark, ys, xs, (w, h) = _mark_pixels(raw)
    _unpaint(saved)                                      # 量完就还原（不改几何）
    # [EN] Restore after measuring (do not change geometry)
    page.update()
    await asyncio.sleep(0.4)

    ok('C1 ★★★ 三个菜单按钮**真的画在屏幕上**了（标记色法：只动颜色不动几何）',
       n_mark >= 60, f'标记色像素 {n_mark}（至少 3 个 16px 图标）')
    ok('C2 ★★ 它们落在**对话框上部那一条栏头带**里',
       bool(ys) and min(ys) >= h * 0.05 and max(ys) <= h * 0.5,
       f'y∈[{min(ys) if ys else "-"},{max(ys) if ys else "-"}] 屏高 {h}')
    # ★★ C3 的**口径**（2026-10-11 改）：原来写的是"三个按钮的 x 跨度 ≥ 屏宽 15%"。
    #   那是按**改之前**的版面标定的 —— 当时四栏因为 `expand` 把 `width` 吃掉而**等宽**
    #   （各 ~442px），三个按钮分散在两栏的宽栏头上，跨度自然大。
    #   2026-10-11 用户要求「第 1 2 3 列适当收窄」，第 2/3 栏缩到 200/130 之后，
    #   跨度变成 285px = 屏宽 14.8%，**刚好跌破 15%** ⇒ 判据假红，
    #   而它想守的那件事（"分属两栏、不是挤在一处"）其实**完全成立**。
    #   ⇒ 改成量**意图**而不是量"一个按旧版面标定过的百分比"：
    #     把标记色的 x 分布分**簇**，要求 ≥ 2 簇、且簇间距 > 100px。
    #     挤在同一栏时只会有一簇（间距≈图标间隔）⇒ 该红还是红。
    # [EN] ★★ C3's **convention** (changed 2026-10-11): it used to read "the three buttons' x span is
    # [EN] >= 15% of the screen width". That was calibrated against the layout **before** the change --
    # [EN] back then the four columns were **equal** because `expand` ate `width` (~442px each), so the
    # [EN] three buttons sat on wide headers in two columns and the span was naturally large.
    # [EN] On 2026-10-11 the user asked to "narrow columns 1 2 3"; after columns 2/3 shrank to 200/130
    # [EN] the span became 285px = 14.8% of the screen, **just below 15%** ⇒ a false red, while the
    # [EN] thing it guards ("in two columns, not crammed together") is **entirely true**.
    # [EN] ⇒ Change it to measure the **intent** rather than "a percentage calibrated against the old
    # [EN] layout": cluster the marker colors' x distribution and require >= 2 clusters with an
    # [EN] inter-cluster gap > 100px. Crammed in one column there'd be a single cluster (gaps ~= icon
    # [EN] spacing) ⇒ it still goes red when it should.
    clusters: list = []
    for x in sorted(xs):
        if clusters and x - clusters[-1][-1] <= 40:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    gaps = [clusters[i + 1][0] - clusters[i][-1] for i in range(len(clusters) - 1)]
    ok('C3 ★★ 它们**横向分开**（分属两栏，不是挤在一处）'
       '—— 判据按"簇的个数与间距"量，不按"占屏宽百分之几"',
       len(clusters) >= 2 and bool(gaps) and max(gaps) > 100,
       f'x∈[{min(xs) if xs else "-"},{max(xs) if xs else "-"}] 屏宽 {w} · '
       f'{len(clusters)} 簇 · 簇间距={gaps}')

    # ── D 存档 ──────────────────────────────────────────────────
    # [EN] ── D Archive ──────────────────────────────────────────────────
    raw = await page.take_screenshot()
    if raw:
        p = OUT / 'usage_filters.png'
        Image.open(io.BytesIO(raw)).convert('RGB').save(p)
        ok('D1 截图落盘（给人看的那一份）', p.is_file(), str(p))


def _finish() -> int:
    p = OUT / 'usage_filters_report.json'
    p.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n用量·栏头筛选验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}')
    return 0 if not bad else 2


async def main(page: ft.Page) -> None:
    code = 1
    tmp = Path(tempfile.mkdtemp(prefix='nws_usagef_'))
    try:
        await _body(page, tmp)
        code = _finish()
    except BaseException:                                # noqa: BLE001
        # ★ 崩溃必须自己留一条红 —— 否则"全绿"和"崩了"在汇总里长得一样。
        # [EN] ★ A crash must leave its own red line — otherwise "all green" and "crashed" look the same in the
        # [EN] summary.
        REPORT['checks'].append({'name': '★ 真机段崩了（自己留一条红）', 'ok': False,
                                 'detail': traceback.format_exc()[-900:]})
        code = _finish()
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)
        await shutdown(page, code=code)


if __name__ == '__main__':
    ft.run(main)
