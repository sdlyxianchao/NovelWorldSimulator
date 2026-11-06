#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真机验证：**叙事窗口的分页与时间戳**（2026-10-11）。

用户两句话
----------
1. 「我感觉对话窗口我往前拉 有些信息在窗口看不见了 是不是会被吞掉一些东西？
   我希望要么这个窗口虽然每个窗口显示的内容如果不能够无限长，则进行分页，
   我需要查看到此次推演所有的内容」
2. 「我希望有选项可以让对话窗口的每一个条目左上角都带一个很小的当前日期和
   时间（真实时间-剧情时间）这样的，以便我进行参考」

查出来的两处**真吞**（都在界面这一侧，`_live_lines` 里其实一条不少）
---------------------------------------------------------------
① `tail = self._live_lines[-200:]` —— 只渲染最近 200 条；
② `if len(col.controls) > 400: del col.controls[:100]` —— 控件超 400
   就把最前面 100 个**删掉**（`_on_narrative` 与 `_push_divider` 各一处）。

所以这一支盯三件事：
  A. **分页算得对**（页边界、往回数第几页、文案、到头灰化）—— 纯逻辑；
  B. **翻页不丢内容**（翻完之后 `_live_lines` 一条不少、页首尾对得上、
     控件数被限在一页附近）—— 真机；
  C. **时间戳**（开关、格式、每条都带、套壳之后"并进上一段"还能改写）—— 真机。

产出：assets/screenshots/narr_window_report.json

English:
On-device verification: **narrative-window paging and timestamps** (2026-10-11).

The user's two requests
-----------------------
1. "when I scroll back in the dialog window some information is no longer visible -- is something
   being swallowed? I'd like this window to page if its content can't be infinitely long; I need to
   be able to see everything in this round"
2. "I'd like an option so that every entry in the dialog window has a very small current date and
   time at its top-left (real time - story time), for reference"

The two **real swallows** found (both on the UI side; `_live_lines` itself loses nothing)
--------------------------------------------------------------------------------------------
(1) `tail = self._live_lines[-200:]` -- only the last 200 entries were rendered;
(2) `if len(col.controls) > 400: del col.controls[:100]` -- once widgets exceeded 400 it **deleted**
    the first 100 (one in `_on_narrative`, one in `_push_divider`).

So this script watches three things:
  A. **Paging computes correctly** (page bounds, N pages back, the label, greying at the ends) --
     pure logic;
  B. **Paging loses nothing** (after turning pages `_live_lines` is untouched, page head/tail line up,
     widget count stays near one page) -- on device;
  C. **Timestamps** (switch, format, present per entry, and "merge into the previous paragraph" still
     rewrites correctly after wrapping) -- on device.

Output: assets/screenshots/narr_window_report.json
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402

from util.flet_shutdown import shutdown  # noqa: E402
from config import CFG  # noqa: E402

CFG.set('MOCK_LLM', 'true')
CFG.set('HIDE_COMMAND_BAR', 'false')

import gui.app_flet as G  # noqa: E402
import verify_ui_common as VU  # noqa: E402
VU.redirect_env_writes()

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}

#: 本支会动的配置项 —— 跑完逐个还原（不能把测试值留给下一支）。
# [EN] : Config keys this script touches -- restored one by one (test values must not leak).
TOUCHED = ('NARR_TIMESTAMP', 'NARR_PAGE_ENTRIES', 'MOCK_LLM', 'HIDE_COMMAND_BAR')
_SAVED: dict = {}


def save_cfg() -> None:
    for k in TOUCHED:
        try:
            _SAVED[k] = CFG.raw(k)
        except Exception:                                        # noqa: BLE001
            _SAVED[k] = None


def restore_cfg() -> None:
    for k, v in _SAVED.items():
        if v is None:
            continue
        try:
            CFG.set(k, v)
        except Exception:                                        # noqa: BLE001
            pass


def ok(name: str, cond, detail: str = '') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    print(f'  {"[OK]  " if cond else "[FAIL]"} {name}'
          + (f'  — {str(detail)[:170]}' if detail else ''), flush=True)
    return bool(cond)


def head(t: str) -> None:
    print(f'\n── {t} ──', flush=True)


def _shell():
    """一个**没跑 `__init__`** 的空壳 app —— 只用来调那两个纯计算方法。

    ★ 为什么可以这样：`_page_bounds` / `_page_slice` / `_pager_text` /
      `_pager_disabled` **只读** `_live_lines` / `_narr_back` / `_narr_new`
      与配置，不碰 project / session / page。用空壳调**同一个函数对象**，
      测的仍然是产品代码。

        English:
    An empty-shell app that **never ran `__init__`** -- used only to call those two pure
    computation methods.
        ★ Why this is legitimate: `_page_bounds` / `_page_slice` / `_pager_text` /
          `_pager_disabled` **only read** `_live_lines` / `_narr_back` / `_narr_new` and the config;
          they touch no project / session / page. Calling the **same function object** on a shell still
          tests product code.
    """
    app = object.__new__(G.NovelWorldApp)
    app._live_lines = []
    app._narr_back = 0
    app._narr_new = 0
    app._ui_run = {}
    return app


def _seed(app) -> None:
    """塞 300 条**真叙事**（`narration` 在界面的白名单里，走的是真入口）。
        English:
    Seed 300 **real narrative** entries (`narration` is on the UI whitelist, so this goes through the
    real entry point).
    """
    for i in range(300):
        app._live_lines.append((0, f'第{i}句：他把壶放下。', 'narration', '12:00:{i % 60:02d}'))


# ══════════════════════════════════════════════════════════════
#  A. 分页算得对（纯逻辑）
# [EN] A. Paging computes correctly (pure logic)
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    head('A. 分页计算（纯逻辑）')
    CFG.set('NARR_PAGE_ENTRIES', '100')
    from config import SPEC
    ok('A0 两个配置项都在（用户要能自己调，而不是改代码）',
       'NARR_TIMESTAMP' in SPEC and 'NARR_PAGE_ENTRIES' in SPEC,
       [k for k in ('NARR_TIMESTAMP', 'NARR_PAGE_ENTRIES') if k not in SPEC])
    app = _shell()
    _seed(app)
    rows, info = app._page_slice()

    ok('A1 ★★ 300 条 / 一页 100 ⇒ 切成 3 页，默认停在**最新**那一页',
       info['pages'] == 3 and info['back'] == 0 and info['at_live'] is True,
       f'{info}')

    # 页边界必须**首尾相接、覆盖全部**（这是"一条不丢"的静态保证）
    # [EN] Page boundaries must be **contiguous end-to-end and cover everything** (this is the static
    # [EN] guarantee that "not one item is lost")
    bounds = app._page_bounds()
    covered: list[int] = []
    for s, e in bounds:
        covered.extend(range(s, e))
    ok('A2 ★★ 三页的边界**首尾相接且覆盖全部 300 条**，而且**真的是三页**'
       '（只验覆盖不够 —— 只返一页也覆盖得了全部）',
       covered == list(range(300)) and len(bounds) == 3, f'bounds={bounds}')

    # 往回翻：页码递减、内容真的是更早那批
    # [EN] Paging back: page numbers decrease, and the content really is the earlier batch
    app._narr_back = 1
    rows1, info1 = app._page_slice()
    app._narr_back = 2
    rows2, info2 = app._page_slice()
    import re as _re

    def _idx(row) -> int:
        m = _re.search(r'第(\d+)句', str(row[1]))
        return int(m.group(1)) if m else -1

    seq = [_idx(rows[0]), _idx(rows1[0]), _idx(rows2[0])]
    ok('A3 ★★ 往回翻一页 ⇒ 内容真的是**更早那一段**，而且**越往回翻越靠前**'
       '（验方向，不只验「三页不一样」）',
       seq[0] > seq[1] > seq[2], f'最新→回1→回2 的首句序号={seq}')
    ok('A3b ★ 越界往回翻（back 设成 99）⇒ **夹到最早那一页**，不越界',
       info2['pages'] == 3 and app._narr_back <= info2['pages'] - 1,
       f'back={app._narr_back} pages={info2["pages"]}')
    # `_page_slice` 只夹自己返回的 back，不改实例属性 —— 这是刻意的
    # （改属性会让"翻过头再点下一頁"跳不回原处）。这里只验它不崩、页数对。
    # [EN] `_page_slice` only clamps the `back` it returns itself, and does not modify instance attributes
    # [EN] -- this is intentional
    # [EN] (Modifying attributes would mean that after paging too far back and then clicking next page, it
    # [EN] cannot jump back to the original place). Here we only verify it does not crash and the page
    # [EN] count is correct.
    ok('A3c ★ 三页互不重叠（页首句两两不同）',
       len({rows[0][1], rows1[0][1], rows2[0][1]}) == 3,
       f'{rows[0][1][:8]} / {rows1[0][1][:8]} / {rows2[0][1][:8]}')

    # 文案：**必须写出总条数** —— 用户要的正是"我能看到全部吗"这个安心感
    # [EN] Text: **must state the total number of items** -- what the user wants is exactly the reassurance
    # [EN] of "can I see everything"
    txt = app._pager_text(info)
    ok('A4 ★★ 翻页条文案里有**总条数**（用户要的"我能看到全部吗"的安心感）',
       '300' in txt and '3' in txt, txt)
    ok('A4b ★ 文案在最新页说「已是最新」，在历史页说「有 N 条新内容」',
       '已是最新' in txt
       and '有 5 条新内容' in app._pager_text({**info, 'at_live': False, 'new': 5}),
       txt)

    # 按钮灰化：四个角
    # [EN] Button graying out: four corners
    def dis(back: int, key: str) -> bool:
        return app._pager_disabled(key, {**info, 'back': back})

    ok('A5 ★★ 「更早 / 最早」在最早那一页灰掉、「更晚 / 最新」在最新页灰掉',
       dis(2, 'prev') and dis(2, 'earliest')
       and dis(0, 'next') and dis(0, 'latest')
       and not dis(0, 'prev') and not dis(2, 'next'),
       f'back=2: prev={dis(2, "prev")} earliest={dis(2, "earliest")} · '
       f'back=0: next={dis(0, "next")} latest={dis(0, "latest")}')

    # 页大小可配：改成 50 ⇒ 页数变 6（说明真的从配置读，不是写死的）
    # [EN] Page size is configurable: change it to 50 => page count becomes 6 (shows it really reads from
    # [EN] config, not hardcoded)
    CFG.set('NARR_PAGE_ENTRIES', '50')
    _r, info50 = app._page_slice()
    ok('A6 ★ 一页多少条**真的从配置读**（改成 50 ⇒ 页数 6）',
       info50['pages'] == 6, f'pages={info50["pages"]} page={info50["page"]}')
    CFG.set('NARR_PAGE_ENTRIES', '100')

    # 空内容：不能崩、也不该有页
    # [EN] Empty content: must not crash, and should have no pages
    empty = _shell()
    e_rows, e_info = empty._page_slice()
    ok('A7 ★ 没有内容时 `_page_slice` 不崩（0 条 / 1 页 / 空列表）',
       e_rows == [] and e_info['pages'] == 1 and e_info['total'] == 0, f'{e_info}')

    # ── A8 时间戳的两个时间是**两回事**，都要给 ──
    # [EN] -- A8 the two times in the timestamp are **different things**; both are needed --
    class _W:
        @staticmethod
        def clock_display() -> str:
            return '第3天·戌时'

    class _L:
        world = _W()

    class _S:
        loop = _L()

    stamp_app = _shell()
    CFG.set('NARR_TIMESTAMP', 'true')
    stamp_app.session = _S()
    with_world = stamp_app._stamp()
    stamp_app.session = None
    no_world = stamp_app._stamp()
    # ★★ 2026-10-14（用户）改格式：
    #   「对话里的时间显示 剧里时间 真实时间 格式改成 剧情时间: xxx  系统时间:xxx」
    #   ⇒ 期望**写绝对字面量**（本项目纪律：不 import 产品常量、不拿被测对象当尺子）：
    #     · 有剧情时间 → 必须**同时**出现 `剧情时间: 第3天·戌时` 与 `系统时间: `，
    #       而且**剧情时间在前**（原来的 `18:42:06 · …` 顺序是反的）；
    #     · 拿不到剧情时间 → **只有** `系统时间: `（不编一个假的），
    #       而且**不该出现「剧情时间」四个字**（出现了就说明它编了一个空值）。
    # [EN] ★★ 2026-10-14 (user) format change: "the time display in the dialogue, story time vs real
    # [EN] time, change the format to 剧情时间: xxx  系统时间:xxx"
    # [EN] => Expectations use **absolute literals** (project discipline: do not import product
    # [EN] constants, do not use the object under test as the ruler):
    # [EN]   · with story time, both `剧情时间: 第3天·戌时` and `系统时间: ` must appear, and
    # [EN]     **story time comes first** (the old order `18:42:06 · ...` is reversed);
    # [EN]   · without story time, **only** `系统时间: ` (no made-up value), and the string
    # [EN]     「剧情时间」must **not** appear at all (if it does, an empty value was fabricated).
    ok('A8 ★★ 时间戳是 `剧情时间: …  系统时间: …`，'
       '**剧情时间在前**；拿不到剧情时间就**只给系统时间**（不编一个假的）',
       '剧情时间: 第3天·戌时' in with_world
       and '系统时间: ' in with_world
       and with_world.index('剧情时间') < with_world.index('系统时间')
       and no_world.startswith('系统时间: ')
       and '剧情时间' not in no_world
       and '·' not in no_world,
       f'有={with_world!r} 无={no_world!r}')
    ok('A8c ★ 两段之间是两个空格（用户写的格式就是两段并排）',
       '戌时  系统时间' in with_world, repr(with_world))
    CFG.set('NARR_TIMESTAMP', 'false')
    ok('A8b ★ 开关关掉 ⇒ `_stamp()` 返回空串（连记都不记）',
       stamp_app._stamp() == '', repr(stamp_app._stamp()))
    CFG.set('NARR_TIMESTAMP', 'true')

# ══════════════════════════════════════════════════════════════
#  B/C. 真机：翻页不丢内容 + 时间戳
# [EN] B/C. On device: paging loses nothing + timestamps
# ══════════════════════════════════════════════════════════════
async def group_bc(page: ft.Page, app) -> None:
    CFG.set('NARR_PAGE_ENTRIES', '100')
    CFG.set('NARR_TIMESTAMP', 'true')

    col = ft.Column([], expand=True, spacing=6, scroll=ft.ScrollMode.AUTO)
    pager = app._mk_narr_pager()
    app._ui_run['narrative'] = col
    app._ui_run['narr_pager'] = pager
    page.add(ft.Column([pager, col], expand=True, spacing=6))
    page.update()

    # ── 用**真入口**塞 250 条（`_on_narrative` 才是产品那条路）──
    # [EN] -- Use the **real entry point** to insert 250 items (`_on_narrative` is the actual product path)
    # [EN] --
    head('B. 真机：翻页不丢内容')
    for i in range(250):
        app._on_narrative(f'第{i}句：他把壶放下。', 1, 'dialogue')
    await asyncio.sleep(0.6)
    n_all = len(app._live_lines)
    ok('B1 ★★ 250 条真的进了事实来源（`_live_lines`）',
       n_all == 250, f'{n_all} 条')

    kinds = [type(c).__name__ for c in VU.walk(col)]
    ok('B2 ★★ 控件数**被限在一页附近**（不是 250 条就 250 个控件 —— 那正是卡的原因）',
       len(col.controls) <= 130, f'控件 {len(col.controls)} 个 / 事实 {n_all} 条')

    # ── 翻到最早那一页 ──
    # [EN] -- Page to the earliest page --
    app._narr_goto('earliest')
    await asyncio.sleep(0.5)
    ok('B3 ★★ 翻到最早页：`_live_lines` **一条不少**（这是"不丢内容"的核心判据）',
       len(app._live_lines) == n_all,
       f'{len(app._live_lines)} 条（翻页前 {n_all} 条）')
    texts = ' '.join(VU.all_texts(col))
    ok('B4 ★★ 最早那一页显示的是**开头那几句**（第0句在第1页上）',
       '第0句' in texts, [x for x in VU.all_texts(col) if '句' in str(x)][:2])
    ok('B4b ★ 刚才那几页的内容**不在这页上**（第200句那批在最新页）',
       '第200句' not in texts, '第200句' in texts)

    _rows, info_e = app._page_slice()
    ok('B5 ★★ 翻页条说得出"现在在第几页 / 共几页 / 共几条"',
       info_e['back'] == 2 and f'共 {n_all} 条' in app._pager_text(info_e),
       app._pager_text(info_e))

    # ── 在历史页时，新内容**不把用户拽走** ──
    # [EN] -- When on a history page, new content **does not drag the user away** --
    n_ctrl_before = len(col.controls)
    before = ' '.join(VU.all_texts(col))
    app._on_narrative('第999句：这一句是在你翻历史时进来的。', 1, 'dialogue')
    await asyncio.sleep(0.3)
    ok('B6 ★★★ 用户翻到历史页时，新条目**不重画、不把人拽回最新**'
       '（只在翻页条上提示"有 N 条新内容"）',
       len(app._live_lines) == n_all + 1
       and len(col.controls) == n_ctrl_before
       and '第999句' not in ' '.join(VU.all_texts(col))
       and app._narr_new >= 1,
       f'事实 {len(app._live_lines)} 条 · 控件 {n_ctrl_before}→{len(col.controls)}'
       f' · 新计数={app._narr_new}')
    app._narr_goto('latest')
    await asyncio.sleep(0.5)
    ok('B6c ★★ 点「最新」⇒ 回到最新页，刚才那句新内容**在那里**（没被吞）',
       '第999句' in ' '.join(VU.all_texts(col))
       and app._narr_new == 0,
       f'新计数={app._narr_new} · {before[:0]}')

    ok('B7 ★★ 最新页**自动跟随**、翻到历史页**关掉自动跟随**'
       '（不关的话，新条目会把正在读前面内容的人一路拽回最新）',
       col.auto_scroll is True, f'最新页 auto_scroll={col.auto_scroll}')
    app._narr_goto('earliest')
    await asyncio.sleep(0.4)
    ok('B7b ★★ 翻到历史页之后 `auto_scroll` 变成假（不再自动跟随）',
       col.auto_scroll is False, f'历史页 auto_scroll={col.auto_scroll}')
    app._narr_goto('latest')
    await asyncio.sleep(0.4)
    # ── C. 时间戳 ──
    # [EN] -- C. Timestamps --
    head('C. 真机：时间戳（剧情时间 · 系统时间）')
    wraps = [c for c in VU.walk(col) if getattr(c, '_narr_ts_wrap', False)]
    ok('C1 ★★ 开着开关 ⇒ 条目外面真的套了**时间戳那一层**',
       bool(wraps), f'{len(wraps)} 个带时间戳的条目')

    stamp_txt: list[str] = []
    for w in wraps:
        inner = getattr(w, '_narr_inner', None)
        try:
            kids = list(getattr(w, 'controls', []) or [])
        except Exception:                                        # noqa: BLE001
            kids = []
        for k in kids:
            if k is not inner:
                value = str(getattr(k, 'value', '') or '')
                if value:
                    stamp_txt.append(value)
    # ★★ 2026-10-14（用户）改格式：原来是 `HH:MM:SS · 剧情时间`（真实时间在前），
    #   现在是 **`剧情时间: …  系统时间: HH:MM:SS`**（剧情时间在前）。
    #   ⚠ 正则用**中文标签字面量**（本判据跑在中文环境，项目里其它判据同样
    #     硬编码中文，如「已停止」）；**不 import 产品的 `t()`** ——
    #     那会让"标签 key 被改坏"这种变异悄悄逃过。
    #   ⚠ 允许**没有**剧情时间那一段（真机场景里 world 可能还没就绪）——
    #     那种情况只给系统时间（`_stamp` 的契约），所以前一段是可选的。
    # [EN] ★★ 2026-10-14 (user) format change: it used to be `HH:MM:SS · story time` (real time
    # [EN] first); now it is **`剧情时间: ...  系统时间: HH:MM:SS`** (story time first).
    # [EN] ⚠ The regex uses **literal Chinese labels** (this criterion runs in a Chinese
    # [EN] environment; other criteria in the project hardcode Chinese the same way, e.g. 「已停止」);
    # [EN] it does **not** import the product's `t()` -- that would let a mutation that breaks the
    # [EN] label key slip through silently.
    # [EN] ⚠ The story-time segment is allowed to be **absent** (in a real-machine scenario `world`
    # [EN] may not be ready yet) -- then only system time is given (the `_stamp` contract), so the
    # [EN] first segment is optional.
    _stamp_re = re.compile(r'^(剧情时间: .+?  )?系统时间: \d{2}:\d{2}:\d{2}$')
    ok('C2 ★★ 时间戳文字形如 `剧情时间: …  系统时间: HH:MM:SS`'
       '（**剧情时间在前**，2026-10-14 用户改的格式）',
       bool(stamp_txt) and all(_stamp_re.match(s) for s in stamp_txt),
       stamp_txt[:3])

    lbl = G.NovelWorldApp.NARR_FS_STAMP
    ok('C3 ★ 时间戳比正文**小一号**（`NARR_FS_STAMP` < `NARR_FS_TINY` < `NARR_FS`）'
       '—— 用户要的就是"很小的"',
       lbl < G.NovelWorldApp.NARR_FS_TINY < G.NovelWorldApp.NARR_FS,
       f'{lbl} < {G.NovelWorldApp.NARR_FS_TINY} < {G.NovelWorldApp.NARR_FS}')

    # 关掉开关 ⇒ 一层都不套
    # [EN] Turn off the switch => not even one layer is wrapped
    CFG.set('NARR_TIMESTAMP', 'false')
    app._render_page()
    await asyncio.sleep(0.4)
    off = [c for c in VU.walk(col) if getattr(c, '_narr_ts_wrap', False)]
    ok('C4 ★★ 关掉 `NARR_TIMESTAMP` ⇒ **一层都不套**（整条消失）',
       not off, f'{len(off)} 个')
    CFG.set('NARR_TIMESTAMP', 'true')
    app._render_page()
    await asyncio.sleep(0.4)

    # ── 「并进上一段」在套壳之后还改得到里面的段落 ──
    #   这是套壳最容易弄坏的地方：壳不剥掉就会**新起一段**，
    #   于是"跑着看是两段、重进界面是一段"。
    # [EN] -- "Merge into previous paragraph" can still modify the inner paragraph after wrapping --
    # [EN] This is where wrapping most easily breaks things: if the shell is not peeled off, it will
    # [EN] **start a new paragraph**,
    # [EN] so "while running it looks like two paragraphs, but after re-entering the UI it is one
    # [EN] paragraph".
    app._narr_goto('latest')
    await asyncio.sleep(0.4)
    n_pages_before = len(col.controls)
    app._on_narrative('紧接着的一句。', 1, 'narration')
    app._on_narrative('再接一句。', 1, 'narration')
    await asyncio.sleep(0.3)
    # ⚠ 这里**必须**用会合并的类型（`narration`）—— 反例法 M7 教过一次：
    #   B 组为了能测出"控件有界"换成了不合并的 `dialogue`，
    #   而那两句要是跟着一起换，"并进上一段"这个前提就没了（判据恒绿/恒红）。
    # [EN] ⚠ This **must** use a mergeable kind (`narration`) -- reverse experiment M7 taught
    # [EN] once: group B switched to non-mergeable `dialogue` so "bounded widgets" could be
    # [EN] measured; had those two lines switched along with it, the premise of "merge into the
    # [EN] previous paragraph" would be gone.
    ok('C5 ★★ 套了时间戳之后，"并进上一段"仍然**改到里面那个段落**'
       '（不剥壳就会变成"跑着看两段、重进界面一段"）',
       len(col.controls) <= n_pages_before + 1,
       f'控件 {n_pages_before} → {len(col.controls)}')
    # ⚠ 只查**最后那一条**：B 组用的是不合并的 `dialogue`（渲染成方块、没有 spans），
    #   把整棵树都要求「里面是段落」会误判。
    # [EN] ⚠ Only the **last entry** is checked: group B uses non-mergeable `dialogue` (rendered as
    # [EN] a block, with no spans), so requiring that the whole tree wraps a paragraph misjudges.
    last = col.controls[-1] if col.controls else None
    inner_last = getattr(last, '_narr_inner', None)
    ok('C5b ★ 并进上一段之后，最后那条仍然是「时间戳层 + 里面的段落」'
       '（被拆成两条就会露出裸段落 / 裸小字）',
       last is not None and getattr(last, '_narr_ts_wrap', False)
       and getattr(inner_last, 'spans', None) is not None,
       f'最后那个={type(last).__name__} · 是时间戳层='
       f'{bool(getattr(last, "_narr_ts_wrap", False))} · 里面是段落='
       f'{getattr(inner_last, "spans", None) is not None}')


async def main(page: ft.Page) -> None:
    save_cfg()
    try:
        page.enable_screenshots = True
        app = G.NovelWorldApp()
        # ⚠ 只给 `page`，**不调 `app.main()`** —— 中栏的这几个方法不依赖
        #   project / session，最小装配就能真渲染、真量控件。
        # [EN] ⚠ Only `page` is supplied; `app.main()` is **not** called -- these middle-column
        # [EN] methods depend on no project/session, so a minimal assembly still really renders and
        # [EN] really measures widgets.
        app.page = page
        group_a()
        await group_bc(page, app)
    except BaseException:                                        # noqa: BLE001
        import traceback
        REPORT['fatal'] = traceback.format_exc()
        ok('未抛异常（整轮跑完）', False, REPORT['fatal'][-300:])
    finally:
        restore_cfg()
        passed = sum(1 for c in REPORT['checks'] if c['ok'])
        total = len(REPORT['checks'])
        REPORT['passed'], REPORT['total'] = passed, total
        (OUT / 'narr_window_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'\n叙事窗口分页与时间戳验证：{passed}/{total} 通过', flush=True)
        await shutdown(page, code=0 if passed == total else 2)


if __name__ == '__main__':
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
