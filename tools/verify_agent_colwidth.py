# -*- coding: utf-8 -*-
"""真机验证：**剧组 Agents 那张表的列宽**（2026-10-13 用户点名的这一轮）。

用户原话（逐条对上）：

1. 「天机的剧组Agents 档位列和标记列 各减少10px列宽」
2. 「书斋的剧组Agents 档位和模型各减10px … 产出条宽 10px」
3. 「我不想有横向滚动条」
4. 「标记改成2行高度 现在文字显示不全」
5. 「天机的剧组Agents和书斋的剧组Agents都可以调整列宽」
6. 「我希望调整好的列宽可以保存下来，后续打开还是这个宽度」

分四节：

    A 算术：三套 delta 的**幅度与守恒**（不用渲染，快且稳）
    B 控件树：标记列真 2 行；每一格都套了紧约束的 Container（不横滚的机制保障）
    C 真机量：**横向溢出 = 0**（`OnScrollEvent` 自报，不靠找那条灰带）
    D 真机量：拖拽生效、松手存盘、**重开还是那个宽**、两表各存一套

★ 判据纪律（2026-10-13 那轮 5 条变异不红的教训）：
  期望一律写**绝对字面量**（−10 / 0 / 40 / 2），不写"从产品 import 来的常量再算一遍"
  —— 变异那个常量时判据的期望跟着一起动 ⇒ 自证假绿。
  唯一例外：宽度**总和**那条用「avail − 24 − 2 − 16」这样的字面量算式，
  同样不 import `AGENT_BOX_*`。

★ 为什么 C 节用 `OnScrollEvent` 而不是"找滚动条那条灰带"：
  灰带法在本项目已经返工两次 —— ① 数"表头带里的竖边框线"被新加的拖拽缝干扰，
  读数不可靠；② 改 A/B 对照后，"正常"组里也有一条 8px 带子，分不清是不是滚动条。
  `OnScrollEvent` 是**框架自己报的数**：
      横向溢出 = max_scroll_extent − min_scroll_extent
  （⚠ 别再减一次 `viewport_dimension` —— Flutter 的 `maxScrollExtent` **已经是**
    「内容 − 视口」，减两次会变负数。第一版就写错。）
  它跟颜色、主题、缩放全都无关，也能给出**溢出多少**这个连续量。

产出：assets/screenshots/agent_colwidth_report.json
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

from config import CFG                                       # noqa: E402
CFG.set('MOCK_LLM', 'true')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

import gui.app_flet as AF                                    # noqa: E402
from gui.app_flet import (                                   # noqa: E402
    NovelWorldApp, AGENT_COLS, AGENT_COL_DELTA_TIANJI,
    AGENT_COL_DELTA_BOOK, _agent_col_widths, _agent_colw_file,
    _load_agent_colw, _save_agent_colw, _reset_agent_colw,
    _agent_col_delta, book_geometry, tianji_geometry,
)
from store.project import Project                            # noqa: E402
from i18n import set_lang, t                                 # noqa: E402
set_lang(_lang)

import verify_ui_common as VU                                # noqa: E402
from util.flet_shutdown import shutdown                      # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

# 格子之间那道间距（`DataTable.column_spacing`）—— 写死成字面量，
# 不 import 产品常量（见文件头的判据纪律）。
# [EN] The gap between cells (`DataTable.column_spacing`) -- hard-coded as a literal,
# [EN] not imported from the product (see the criterion discipline at the top of this file).
COL_GAP = 14
N_COL = len(AGENT_COLS)
# 盒子的"外圈"：右边让出的车道 + 左右边框 + 左右内边距（字面量，不 import）
# [EN] The box's "outer ring": the yielded lane on the right + L/R borders + L/R padding
# [EN] (literals, not imported)
BOX_OUTSIDE = 24 + 2 + 16

# 拖拽那条：期望"这一列正好多了 40px"，容差 ±4。
# ⚠ 容差必须**小于**最关键变异造成的偏差：把"不存 delta"那种变异打上去会差 40，
#   "存一半"差 20 —— ±4 都抓得住。别写成 ±24（2026-10-13 那轮 D7b 就是容差 24
#   而变异只造成 18px 偏差 ⇒ 假绿）。
# [EN] The drag one: expect "this column gained exactly 40px", tolerance +/-4.
# [EN] ⚠ The tolerance must be **smaller** than the deviation caused by the most critical
# [EN] mutation: a "don't store the delta" mutation deviates by 40, a "store half" one by 20
# [EN] -- +/-4 catches both. Don't write +/-24 (in the 2026-10-13 round D7b had a tolerance of
# [EN] 24 while the mutation only caused an 18px deviation => fake green).
DRAG_EXPECT = 40
DRAG_TOL = 4


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:300]})
    if not cond:
        report['ok'] = False
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'  | {str(detail)[:110]}' if detail else ''), flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A. 算术：三套 delta 的幅度与守恒
# ══════════════════════════════════════════════════════════════
# 任何一列都**不得低于**它（绝对字面量，不 import 产品的 `AGENT_COL_HARD_MIN`）
# [EN] ═══ A. Arithmetic: the three deltas' magnitude and conservation ═══
# [EN] No column may go **below** this (absolute literal, not the product's
# [EN] `AGENT_COL_HARD_MIN`)
HARD_MIN_LIT = 24


def _expect_give(base_v: int, ask: int = 10) -> int:
    """这一列**最多**能让出多少 = `min(要点名的 10px, 让到下限为止还剩多少)`。

    ⚠ 为什么期望不能一律写死 −10：窄屏（avail=520）下十列已经被压到硬下限
      24，再让 10px 就得把某一列压到 14（连一个字都放不下）—— 产品里那条
      `_give = min(-_d, max(0, widths[i] - lows[i]))` 就是干这个的。
      ⇒ 判据跟着"**让到不能再让**"这个真实契约走；而宽屏（真正会用到的档位）
      下必须**正好 −10**，这一条由 A0 单独钉死。

        English:
    How much this column can **at most** yield = `min(the 10px asked for, whatever is left above
    its floor)`.
        ⚠ Why the expectation can't just be a hard −10: on a narrow screen (avail=520) the ten
        columns are already down at the hard floor of 24, and yielding 10 more would push a column
        to 14 (can't fit a single character) -- which is exactly what
        `_give = min(-_d, max(0, widths[i] - lows[i]))` is for.
        => The criterion follows the real contract "**yield until you can't**"; and on a wide
        screen (the width actually used) it must be **exactly −10**, which A0 pins down on its own.
    """
    return min(ask, max(0, int(base_v) - HARD_MIN_LIT))


def arithmetic() -> None:
    print('\n── A 算术：delta 的幅度与守恒 ──')
    for avail in (1668, 904, 520):
        base = _agent_col_widths(avail)
        tj = _agent_col_widths(avail, delta=dict(AGENT_COL_DELTA_TIANJI))
        bk = _agent_col_widths(avail, delta=dict(AGENT_COL_DELTA_BOOK))
        _pre = f'avail={avail}：'
        _wide = (avail == 1668)          # 真实会用到的那一档
        # [EN] The gear that is actually used

        # ★ A0：宽屏下必须**正好 −10**（这才是用户点名的那条；窄屏让不动是契约允许的）
            # [EN] ★ A0: on a wide screen it must be **exactly -10** (that is the one the user
            # [EN] named; a narrow screen not being able to yield is allowed by the contract)
        if _wide:
            ok('A0 ★★★ 宽屏（avail=1668）下点名的列**正好各 −10**'
               '（用户：「档位列和标记列 各减少10px」/「档位和模型各减10px / 产出 10px」）',
               base['tier'] - tj['tier'] == 10
               and base['tag'] - tj['tag'] == 10
               and base['tier'] - bk['tier'] == 10
               and base['model'] - bk['model'] == 10
               and base['feeds'] - bk['feeds'] == 10,
               f"天机 档位−{base['tier'] - tj['tier']}/标记−{base['tag'] - tj['tag']}；"
               f"书斋 档位−{base['tier'] - bk['tier']}/模型−{base['model'] - bk['model']}"
               f"/产出−{base['feeds'] - bk['feeds']}")

        # ── 天机：档位 / 标记 各让 10（让到下限为止）──
            # [EN] ── Tianji: tier / tag each yield 10 (down to the floor) ──
        e_tier = _expect_give(base['tier'])
        e_tag = _expect_give(base['tag'])
        ok(f'A1 ★★ {_pre}天机：档位让出 **{e_tier}px**（到下限为止）',
           base['tier'] - tj['tier'] == e_tier,
           f"实际 −{base['tier'] - tj['tier']} / 期望 −{e_tier}")
        ok(f'A2 ★★ {_pre}天机：标记让出 **{e_tag}px**',
           base['tag'] - tj['tag'] == e_tag,
           f"实际 −{base['tag'] - tj['tag']} / 期望 −{e_tag}")
        _moved_tj = (base['tier'] - tj['tier']) + (base['tag'] - tj['tag'])
        ok(f'A3 ★★ {_pre}天机：让出来的 **{_moved_tj}px** 如数还给提示词（总和守恒）',
           tj['prompt'] - base['prompt'] == _moved_tj
           and sum(tj.values()) == sum(base.values()),
           f"提示词 +{tj['prompt'] - base['prompt']}（期望 +{_moved_tj}）；"
           f'总和 {sum(tj.values())} vs {sum(base.values())}')

        # ── 书斋：档位 / 模型 / 产出 各让 10 ──
            # [EN] ── Study: tier / model / output each yield 10 ──
        b_tier = _expect_give(base['tier'])
        b_model = _expect_give(base['model'])
        b_feeds = _expect_give(base['feeds'])
        ok(f'A4 ★★ {_pre}书斋：档位让出 **{b_tier}px**',
           base['tier'] - bk['tier'] == b_tier,
           f"实际 −{base['tier'] - bk['tier']} / 期望 −{b_tier}")
        ok(f'A5 ★★ {_pre}书斋：模型让出 **{b_model}px**（用户：「模型…各减10px」）',
           base['model'] - bk['model'] == b_model,
           f"实际 −{base['model'] - bk['model']} / 期望 −{b_model}")
        ok(f'A6 ★★ {_pre}书斋：产出让出 **{b_feeds}px**（用户：「产出条宽 10px」）',
           base['feeds'] - bk['feeds'] == b_feeds,
           f"实际 −{base['feeds'] - bk['feeds']} / 期望 −{b_feeds}")
        _moved_bk = ((base['tier'] - bk['tier'])
                     + (base['model'] - bk['model'])
                     + (base['feeds'] - bk['feeds']))
        ok(f'A7 ★★ {_pre}书斋：让出来的 **{_moved_bk}px** 如数还给提示词（总和守恒）',
           bk['prompt'] - base['prompt'] == _moved_bk
           and sum(bk.values()) == sum(base.values()),
           f"提示词 +{bk['prompt'] - base['prompt']}（期望 +{_moved_bk}）")

        # ★ 成对：不是"所有列一起缩了"（那样上面全绿但没意义）
            # [EN] ★ Paired: it isn't "all columns shrank together" (that would pass the
            # [EN] above while meaning nothing)
        ok(f'A8 ★★ {_pre}成对：没点名的列**一个都没动**（英文名/出工/操作）',
           all(tj[k] == base[k] and bk[k] == base[k]
               for k in ('name_en', 'when', 'act')),
           {k: (tj[k], bk[k], base[k]) for k in ('name_en', 'when', 'act')})

        # ── ★★★ 不横滚的**唯一保障**：各列之和 + 间距 == 盒内可用宽 ──
            # [EN] ── ★★★ The **only guarantee** against h-scroll: sum of columns + gaps ==
            # [EN] the box's inner usable width ──
        want = avail - BOX_OUTSIDE
        for tag, w in (('基准', base), ('天机', tj), ('书斋', bk)):
            got = sum(w.values()) + COL_GAP * (N_COL - 1)
            ok(f'A9 ★★★ {_pre}{tag}：Σ列宽 + 间距 == 盒内可用宽 **{want}**'
               '（差一点就横滚）',
               got == want, f'实际 {got} / 期望 {want}（差 {got - want}）')

        # ★★ A10：任何一列都**不得低于 24**（再窄连一个字都放不下）。
        #   为什么总和（A9）之外还要这一条：`_rebalance()` 会把"少了的像素"补给
        #   **最宽**的那一列，于是"某一列被压坏"这件事在总和上**看不出来**
        #   （反例法实测：变异「让出不看下限」时 A9 全绿、只有这条红）。
        # [EN] ★★ A10: no column may go **below 24** (any narrower and not even one character fits).
        # [EN] Why this on top of the sum (A9): `_rebalance()` gives "missing pixels" back to the
        # [EN] **widest** column, so "one column got crushed" is **invisible in the total** (measured
        # [EN] by the counterexample method: with the "ignore the floor when yielding" mutation, A9
        # [EN] stays green and only this one goes red).
        for tag, w in (('基准', base), ('天机', tj), ('书斋', bk)):
            _lo = min(w.values())
            ok(f'A10 ★★ {_pre}{tag}：最窄那一列也**不低于 {HARD_MIN_LIT}**'
               '（让出时"最多让到下限"这条契约真的被守着）',
               _lo >= HARD_MIN_LIT,
               f'最窄 {_lo}（下限 {HARD_MIN_LIT}）；各列 {dict(w)}')


# ══════════════════════════════════════════════════════════════
#  真机：辅助（页签 / 滚动行 / 溢出）
# ══════════════════════════════════════════════════════════════
# [EN] ═══ Real machine: helpers (tabs / scroll row / overflow) ═══
def _tab_index_of(dlg, name: str):
    bar = next((c for c in VU.walk(dlg)
                if isinstance(c, ft.TabBar)), None)
    if bar is None:
        return None
    for i, tb in enumerate(getattr(bar, 'tabs', None) or []):
        if str(getattr(tb, 'label', '') or '').strip() == name:
            return i
    return None


def _goto_crew(page, dlg) -> bool:
    ix = _tab_index_of(dlg, t('剧组 Agents'))
    tb = next((c for c in VU.walk(dlg) if type(c).__name__ == 'Tabs'), None)
    if ix is None or tb is None:
        return False
    tb.selected_index = ix
    page.update()
    return True


def _crew_panel(dlg):
    return VU.tab_panels(dlg).get(t('剧组 Agents'))


def _scroll_row(panel):
    """剧组表外面那层**可横向滚**的 Row（里面得有一张 N 列的剧组表）。"""
    out = [c for c in VU.walk(panel)
           if isinstance(c, ft.Row)
           and getattr(c, 'scroll', None) not in (None,)
           and any(isinstance(x, ft.DataTable)
                   and len(getattr(x, 'columns', None) or []) == N_COL
                   for x in VU.walk(c))]
    return out[0] if out else None


async def _overflow(page, row) -> float | None:
    """★ 用**滚动条自己报的数**量横向溢出（不靠像素、不靠猜颜色）。

    ⚠ `max_scroll_extent` 已经是「内容 − 视口」，**别再减一次 viewport**
      （第一版就是这么写错的，量出来 −1618px）。
    """
    got: dict = {}

    def _on(e):
        got.update({'min': e.min_scroll_extent, 'max': e.max_scroll_extent,
                    'vp': e.viewport_dimension})

    row.on_scroll = _on
    page.update()
    await asyncio.sleep(0.2)
    try:
        await row.scroll_to(offset=1)
    except Exception:                                        # noqa: BLE001
        pass
    page.update()
    await asyncio.sleep(0.6)
    if 'max' not in got:
        return None
    return float(got['max']) - float(got['min'])


async def _open(page, app, book: bool, proj):
    """打开书斋/天机并切到「剧组 Agents」页，返回 `(dlg, panel)`。"""
    app.current_project = proj if book else None
    dlg = (app.show_project_settings() if book
           else app.show_global_settings())
    page.update()
    await asyncio.sleep(0.7)
    if not _goto_crew(page, dlg):
        return dlg, None
    await asyncio.sleep(0.9)
    return dlg, _crew_panel(dlg)


def _close(page) -> None:
    while VU.open_dialogs(page):
        page.pop_dialog()
    page.update()


# ══════════════════════════════════════════════════════════════
#  B. 控件树：标记列 2 行 + 每格都套了紧约束的 Container
# ══════════════════════════════════════════════════════════════
# [EN] ═══ B. Widget tree: tag column on 2 lines + every cell wrapped in a tight Container ═══
def _col_cells(panel, key: str) -> list:
    """某一列在**所有行**（含表头）里的那些 `ft.Text`。"""
    idx = [i for i, c in enumerate(AGENT_COLS) if c[0] == key]
    if not idx:
        return []
    i = idx[0]
    out = []
    for tbl in VU.walk(panel):
        if not isinstance(tbl, ft.DataTable):
            continue
        if len(getattr(tbl, 'columns', None) or []) != N_COL:
            continue
        for row in (getattr(tbl, 'rows', None) or []):
            cells = getattr(row, 'cells', None) or []
            if i < len(cells):
                out += [x for x in VU.walk(cells[i])
                        if isinstance(x, ft.Text)]
    return out


def check_cells(panel, label: str, widths: dict) -> None:
    print(f'\n── B 控件树（{label}）──')
    # ★★ 标记列 2 行（用户：「标记改成2行高度 现在文字显示不全」）
        # [EN] ★★ The tag column on 2 lines (user: "make the tag column 2 lines tall, the
        # [EN] text is cut off right now")
    tag_txts = _col_cells(panel, 'tag')
    ok(f'B1 ★★★ {label}：标记列那一格**最多 2 行**（`max_lines == 2`）',
       bool(tag_txts) and all(getattr(x, 'max_lines', None) == 2
                              for x in tag_txts),
       f'{len(tag_txts)} 格，max_lines='
       f'{[getattr(x, "max_lines", None) for x in tag_txts][:4]}')
    ok(f'B2 ★★ {label}：标记列第 2 行还放不下时给 **…**（`ELLIPSIS`）',
       bool(tag_txts) and all(str(getattr(x, 'overflow', '')).endswith('ELLIPSIS')
                              for x in tag_txts),
       str([getattr(x, 'overflow', None) for x in tag_txts][:2]))
    # ★ 成对：不是"把所有列都改成 2 行"
        # [EN] ★ Paired: it isn't "make every column 2 lines"
    en_txts = _col_cells(panel, 'name_en')
    ok(f'B3 ★★ {label}：成对 —— 英文名列仍是 **1 行**（没把整张表都放开）',
       bool(en_txts) and all(getattr(x, 'max_lines', None) == 1
                             for x in en_txts),
       f'max_lines={[getattr(x, "max_lines", None) for x in en_txts][:4]}')

    # ★★★ 每一格都套了**紧约束的 Container** —— 这是"不横滚"的机制保障：
    #   光给 `ft.Text` 写 `width` 钉不住列宽（Flutter 按格子的**内在宽**定列宽）。
        # [EN] ★★★ Every cell gets a **tight Container** -- the mechanism behind "no h-scroll":
        # [EN] giving `ft.Text` a `width` cannot pin a column (Flutter sizes by **intrinsic
        # [EN] width**).
    bad = []
    for tbl in VU.walk(panel):
        if not isinstance(tbl, ft.DataTable):
            continue
        if len(getattr(tbl, 'columns', None) or []) != N_COL:
            continue
        for row in (getattr(tbl, 'rows', None) or []):
            for i, cell in enumerate(getattr(row, 'cells', None) or []):
                if i >= N_COL:
                    continue
                want = int(widths[AGENT_COLS[i][0]])
                inner = getattr(cell, 'content', None)
                if not isinstance(inner, ft.Container) \
                        or int(getattr(inner, 'width', 0) or 0) != want:
                    bad.append((AGENT_COLS[i][0], want,
                                type(inner).__name__,
                                getattr(inner, 'width', None)))
    ok(f'B4 ★★★ {label}：**每一格**都套了紧约束的 Container，宽 == 算出来的列宽'
       '（不套的话 Flutter 按内容内在宽定列宽 ⇒ 表比盒子宽 ⇒ 横滚）',
       not bad, f'{len(bad)} 格不符：{bad[:4]}')


# ══════════════════════════════════════════════════════════════
#  C. 真机量：横向溢出 == 0
# ══════════════════════════════════════════════════════════════
# [EN] ═══ C. Real machine: horizontal overflow == 0 ═══
async def check_overflow(page, app, proj) -> None:
    print('\n── C 真机：横向溢出（滚动条自己报的数）──')
    for book in (True, False):
        tag = '书斋' if book else '天机'
        dlg, panel = await _open(page, app, book, proj)
        row = _scroll_row(panel) if panel is not None else None
        if row is None:
            ok(f'C ★★★ {tag}：能量到滚动读数', False, '找不到可横滚的 Row')
            _close(page)
            await asyncio.sleep(0.3)
            continue
        ov = await _overflow(page, row)
        # ⚠ 缩放窗口后再量一次：窄屏是"十列下限之和超过预算"那条老病的高发区
            # [EN] ⚠ Measure once more after resizing: a narrow screen is where the old defect
            # [EN] "the ten floors sum past the budget" flares up
        _close(page)
        await asyncio.sleep(0.3)
        page.window.width = 1180
        page.window.height = 760
        page.update()
        await asyncio.sleep(1.2)
        dlg2, panel2 = await _open(page, app, book, proj)
        row2 = _scroll_row(panel2) if panel2 is not None else None
        ov2 = (await _overflow(page, row2)) if row2 is not None else None
        _close(page)
        await asyncio.sleep(0.3)
        page.window.width = 1904
        page.window.height = 1009
        page.update()
        await asyncio.sleep(1.2)
        ok(f'C ★★★ {tag}：宽窗口下**横向溢出 == 0**（没有横向滚动条）',
           ov is not None and abs(ov) < 1.0,
           f'溢出 {ov}px（期望 0）')
        ok(f'C ★★★ {tag}：窄窗口（1180×760）下横向溢出**仍 == 0**',
           ov2 is not None and abs(ov2) < 1.0,
           f'溢出 {ov2}px（期望 0）')


# ══════════════════════════════════════════════════════════════
#  D. 真机：拖拽 + 持久化
# ══════════════════════════════════════════════════════════════
# [EN] ═══ D. Real machine: dragging + persistence ═══
def _grips(panel) -> list:
    return [c for c in VU.walk(panel)
            if isinstance(c, ft.GestureDetector)
            and str(getattr(c, 'mouse_cursor', '')) .endswith('RESIZE_LEFT_RIGHT')]


class _Ev:
    """假的事件对象：拖拽回调只读 `global_position.x`。"""

    def __init__(self, x: float):
        self.global_position = type('P', (), {'x': x, 'y': 0.0})()


async def check_drag(page, app, proj) -> None:
    print('\n── D 真机：拖表头那条缝 + 存盘 + 重开还是那个宽 ──')
    for book in (True, False):
        tag = '书斋' if book else '天机'
        scope = 'project' if book else 'global'
        f = _agent_colw_file(scope, project=(proj if book else None))
        if f.exists():                       # 上一段跑留下的，清掉
        # [EN] Left over from the previous run; clear it out
            try:
                f.unlink()
            except Exception:                # noqa: BLE001
                pass
        dlg, panel = await _open(page, app, book, proj)
        if panel is None:
            ok(f'D ★★★ {tag}：能打开剧组页', False, '页签没切过去')
            _close(page)
            await asyncio.sleep(0.3)
            continue

        # D1：列数 −1 条缝（最后一列右边是车道尽头，不给缝）
            # [EN] D1: column count - 1 seams (right of the last column is the end of the lane,
            # [EN] no seam)
        grips = _grips(panel)
        ok(f'D1 ★★ {tag}：表头有 **{N_COL - 1}** 条可拖的缝（最后一列不给）',
           len(grips) == N_COL - 1, f'实际 {len(grips)} 条 / 期望 {N_COL - 1}')

        # D2：★ 行为判 —— 真的拖一次
            # [EN] D2: ★ behavioral -- really drag it once
        target = 'name_en'                   # 拖「英文名」这一列
        i_t = [i for i, c in enumerate(AGENT_COLS) if c[0] == target][0]
        before = _agent_col_widths(
            tianji_geometry(page)[2] if not book else book_geometry(page)[2],
            delta=_agent_col_delta(scope, project=(proj if book else None)))
        g = grips[i_t] if i_t < len(grips) else None
        if g is None:
            ok(f'D2 ★★★ {tag}：能拖「{target}」那条缝', False, '缝没找到')
        else:
            _down = getattr(g, 'on_horizontal_drag_start', None)
            _move = getattr(g, 'on_horizontal_drag_update', None)
            _up = getattr(g, 'on_horizontal_drag_end', None)
            if not all(callable(x) for x in (_down, _move, _up)):
                ok(f'D2 ★★★ {tag}：三个拖拽回调都在', False,
                   f'{_down}/{_move}/{_up}')
            else:
                _down(_Ev(500.0))
                _move(_Ev(500.0 + DRAG_EXPECT))      # 往右拖 40px
                # [EN] Drag it 40px to the right
                page.update()
                await asyncio.sleep(0.5)
                after = _col_cells(panel, target)
                # 直接从**重建后**的格子上量这一列现在多宽
                    # [EN] Measure how wide this column is now, straight off the **rebuilt** cell
                _w_now = None
                for c in VU.walk(panel):
                    if isinstance(c, ft.Container) \
                            and getattr(c, 'width', None) is not None:
                        pass
                _w_now = _width_of(panel, target)
                d = (int(_w_now) - int(before[target])) if _w_now else None
                ok(f'D2 ★★★ {tag}：往右拖 {DRAG_EXPECT}px ⇒ 「{target}」'
                   f'这一列正好 **+{DRAG_EXPECT}px**（容差 ±{DRAG_TOL}）',
                   d is not None and abs(d - DRAG_EXPECT) <= DRAG_TOL,
                   f'实际 +{d}px（{before[target]} → {_w_now}）')
                _up(_Ev(500.0 + DRAG_EXPECT))
                page.update()
                await asyncio.sleep(0.5)

                # D3：松手 ⇒ 写盘
                    # [EN] D3: releasing the button => write to disk
                saved = _load_agent_colw(scope, project=(proj if book else None))
                ok(f'D3 ★★★ {tag}：松手后**写盘**了（下次打开还是这个宽）',
                   saved is not None
                   and abs(int(saved.get(target, 0)) - DRAG_EXPECT) <= DRAG_TOL,
                   f'盘上 {saved}')

                # D4：★★ 关掉重开 ⇒ 还是那个宽（用户：「后续打开还是这个宽度」）
                    # [EN] D4: ★★ close and reopen => still that wide (user: "still that wide
                    # [EN] next time it opens")
                _close(page)
                await asyncio.sleep(0.4)
                dlg2, panel2 = await _open(page, app, book, proj)
                _w_reopen = _width_of(panel2, target) if panel2 else None
                # ⚠ 期望用**拖完之后实测到的那个宽**（`_w_now`），不是"基准 +40"
                #   —— 后者在 absorber 富余不足时会落空，而那不是这一条要验的东西
                #   （"拖得动多少"由 D2 管，这里只管"重开还在不在"）。
                # [EN] ⚠ The expectation is the width **actually measured after the drag** (`_w_now`),
                # [EN] not "baseline + 40" -- the latter falls apart when the absorber lacks headroom,
                # [EN] which is not what this check is about (D2 covers "how far it can be dragged";
                # [EN] here we only care whether it survives a reopen).
                ok(f'D4 ★★★ {tag}：**关掉重开**后「{target}」仍是拖出来的宽'
                   f'（{_w_now}）',
                   _w_reopen is not None
                   and abs(int(_w_reopen) - int(_w_now)) <= DRAG_TOL,
                   f'重开后 {_w_reopen} / 期望 {_w_now}')

                # D5：★ 「恢复默认列宽」当场回到出厂宽、文件也删了
                # ⚠ Flet 1.0 里**没有** `ft.ElevatedButton`（本项目 `mk_btn` 用的是
                #   `ft.FilledButton`）。按钮文案挂在 `content` 那个 `ft.Text` 上。
                # [EN] ⚠ Flet 1.0 has **no** `ft.ElevatedButton` (this project's `mk_btn` uses
                # [EN] `ft.FilledButton`). The label sits on the `content` Text.
                _btn = next((c for c in VU.walk(panel2)
                             if isinstance(c, (ft.FilledButton, ft.TextButton,
                                               ft.OutlinedButton))
                             and t('恢复默认列宽') in
                             [str(getattr(x, 'value', '') or '')
                              for x in VU.walk(c)
                              if isinstance(x, ft.Text)]), None)
                _click = getattr(_btn, 'on_click', None)
                if not callable(_click):
                    ok(f'D5 ★★ {tag}：有「恢复默认列宽」且能点', False,
                       '按钮没找到')
                else:
                    _click(None)
                    page.update()
                    await asyncio.sleep(0.6)
                    _w_reset = _width_of(panel2, target)
                    ok(f'D5 ★★ {tag}：点「恢复默认列宽」**当场**回到出厂宽'
                       f'（{before[target]}），文件也删了',
                       _w_reset is not None
                       and abs(int(_w_reset) - int(before[target])) <= DRAG_TOL
                       and not f.exists(),
                       f'回到 {_w_reset} / 期望 {before[target]}；'
                       f'文件还在={f.exists()}')
        _close(page)
        await asyncio.sleep(0.3)

    # ── D6：★★ 两张表**各存一套**（改天机的不动书斋）──
        # [EN] ── D6: ★★ the two tables each keep **their own set** (changing Tianji must not
        # [EN] move Study) ──
    print('\n  ── D6 两表各存一套 ──')
    _save_agent_colw('global', {'name_en': 40}, project=None)
    _save_agent_colw('project', {'name_en': 70}, project=proj)
    g_only = _agent_col_delta('global', project=None)
    b_only = _agent_col_delta('project', project=proj)
    ok('D6 ★★★ 天机与书斋**各存一套**列宽（改一个不动另一个）',
       int(g_only.get('name_en', 0)) == 40
       and int(b_only.get('name_en', 0)) == 70,
       f'天机 {g_only} / 书斋 {b_only}')
    _reset_agent_colw('global', None)
    _reset_agent_colw('project', proj)


def _width_of(panel, key: str):
    """这一列现在**实际**多宽：从任意一行的格子上量（套在外面的 Container）。

    ⚠ 用**第一行的格子**，不要用表头 —— 表头那个 `ft.Text` 为了让出拖拽缝
      窄了 `AGENT_COL_GRIP_W`，量它会被那 8px 带偏。
    """
    idx = [i for i, c in enumerate(AGENT_COLS) if c[0] == key]
    if not idx:
        return None
    i = idx[0]
    for tbl in VU.walk(panel):
        if not isinstance(tbl, ft.DataTable):
            continue
        if len(getattr(tbl, 'columns', None) or []) != N_COL:
            continue
        rows = getattr(tbl, 'rows', None) or []
        if not rows:
            continue
        cells = getattr(rows[0], 'cells', None) or []
        if i >= len(cells):
            continue
        inner = getattr(cells[i], 'content', None)
        if isinstance(inner, ft.Container):
            return int(getattr(inner, 'width', 0) or 0)
    return None


# ══════════════════════════════════════════════════════════════
async def main(page: ft.Page) -> None:
    page.enable_screenshots = True
    _iso = Path(tempfile.mkdtemp(prefix='nws_colw_'))
    old_projects = CFG.s('DEFAULT_PROJECTS_DIR')
    try:
        CFG.set('DEFAULT_PROJECTS_DIR', str(_iso))
        VU.isolate_projects_dir(_iso)
        proj = Project(_iso / '列宽验证', '列宽验证')
        proj.write_nwsproj()
        try:
            (proj.settings_dir).mkdir(parents=True, exist_ok=True)
            (proj.settings_dir / '人物.yaml').write_text(
                '人物:\n  - 姓名: 主角\n    性别: 男\n  - 姓名: 阿蘅\n    性别: 女\n',
                encoding='utf-8')
        except Exception as e:                               # noqa: BLE001
            print('造人物失败:', e)

        app = NovelWorldApp()
        app.main(page)
        await asyncio.sleep(2.2)

        arithmetic()

        # ── B：控件树（书斋 + 天机各一次）──
            # [EN] ── B: the widget tree (Study and Tianji, once each) ──
        for book in (True, False):
            tag = '书斋' if book else '天机'
            dlg, panel = await _open(page, app, book, proj)
            if panel is None:
                ok(f'B ★★★ {tag}：能打开剧组页', False, '页签没切过去')
            else:
                _av = (book_geometry(page)[2] if book
                       else tianji_geometry(page)[2])
                _w = _agent_col_widths(_av, delta=_agent_col_delta(
                    'project' if book else 'global',
                    project=(proj if book else None)))
                check_cells(panel, tag, _w)
            _close(page)
            await asyncio.sleep(0.4)

        await check_overflow(page, app, proj)
        await check_drag(page, app, proj)
    except Exception:
        report['ok'] = False
        report['fatal'] = traceback.format_exc()
        report['checks'].append({'name': '★ 脚本跑完了（没有中途崩）',
                                 'ok': False,
                                 'detail': traceback.format_exc()[-300:]})
        print(traceback.format_exc()[-1200:], flush=True)
    finally:
        try:
            CFG.set('DEFAULT_PROJECTS_DIR', old_projects)
        except Exception:                                    # noqa: BLE001
            pass
        VU.safe_rmtree(_iso, ignore_errors=True)

    n_ok = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n剧组表列宽：{n_ok}/{len(report["checks"])}'
          + ('' if report.get('ok', True) else '  ✗ 有失败'))
    (OUT / 'agent_colwidth_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    await shutdown(page, code=0 if report.get('ok', True) else 2)


if __name__ == '__main__':
    ft.run(main)
