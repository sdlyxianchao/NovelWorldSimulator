# -*- coding: utf-8 -*-
"""**用量报表对话框**（用户 2026-10-10 的第二个需求）。

界面（用户逐条指定，这里照做）
------------------------------
    对话框默认最大化；**四栏**，从左到右：

    | 第 1 栏 | 第 2 栏 | 第 3 栏 | 第 4 栏 |
    |---|---|---|---|
    | 软件整体 + 各个项目（多了可滚动） | 按**划分方式**加载统计卡片 | 当前卡片下的各个 **Agent** | **详细统计**（表格） |

    · 第 2 栏的划分：软件整体 **模型 / 日期 / 模块**（3 个）；
      某个项目 **模型 / 日期 / 推演任务 / 模块**（4 个）。

★★ 2026-10-11：**筛选从"顶上集中一排"改成"各栏自己的表头"**
----------------------------------------------------------
用户原话：「关于用量 界面设计有问题，你现在最上面那几个筛选功能，希望是除了最左边列，
中间第二个第三个列都有自己的一套筛选，且用合适的**上下文菜单**的方式放到**每个列的表头上**，
而不是单独放一个地方。」——问过之后用户选了：**第 3 栏同时挂两套菜单**
（时间范围 + Agent 筛选）；第 4 栏（明细表）**不加**表头筛选。

于是：

| 栏 | 栏头（固定在**滚动区之外**） | 菜单 |
|---|---|---|
| 1 | 范围 · 软件整体 + 各项目 | 无（用户点名"除了最左边列"） |
| 2 | 划分 · `模型 ▾` | 该栏的划分方式（3 / 4 项，跟着 scope 变） |
| 3 | Agent · `🗓` `☰` | **时间范围** + **Agent 筛选**（两套都放这一栏） |
| 4 | 明细 · 当前路径 | 无 |

· 菜单走 `ft.PopupMenuButton` + `ft.PopupMenuItem`（**上下文菜单**的形态）：当前项带勾
  （`checked=True`），所以"现在是哪个筛选"在菜单里**读得出来**，不靠记忆；
  栏头下面的小字再复述一遍。
· ⚠ 栏头放在**滚动区之外** —— 这正是"表头"该有的行为：内容滚起来，筛选还钉在顶上。
· ⚠ **「时间范围」作用在四栏**（`day >= since` 是 SQL 里的全局窗口），它挂在第 3 栏
  是**按用户指定的位置**，不是"只影响第 3 栏"。第 3 栏小字也只说"时间范围"，不加限定词。

★ 三条硬约束（用户点名 + 本项目铁律）
------------------------------------
1. **所有数字由数据库直接算，不调模型** —— 界面里一句 LLM 调用都没有
   （`llm/usage` 是纯 SQL）。
2. **不落 md**：只读库、只在内存里拼控件（用户："不要在本地保存 md 等信息，
   默认统计信息存入数据库，需要的时候使用软件动态生成界面各个元素"）。
3. **中英双语**（2026-10-10 补）。

⚠ 这个模块**不 import `gui.app_flet`**（那会循环导入：app_flet 要 import 它来挂入口）。
  配色由调用方以 `colors` 参数传进来 —— `app_flet.C` 就是那份字典。
  ⇒ 需要 `app_flet` 的助手时（`mk_icon_btn` / `dialog_close_side`）**在本文件里
    各留一份等价的**，与 `_pad` / `_border` 同一个理由。判据 `verify_usage_stats`
    的 G6 钉着这条。

★★ 2026-10-10 第二件事：**整窗补双语 + 右上角「×」+ 左栏项目可删**
--------------------------------------------------------------
· 这一窗以前**整窗硬编码中文** —— 是产品里**唯一**一个没做双语的窗口
  （英文界面下满屏中文）。根因不是"忘了翻"，而是**判据从来没打开过它**：
  `verify_ui_english` 那 9 个对话框里没有它，而它自己还因为用了 Flet 1.0 不存在的
  `ft.padding.all` / `page.open()` **一次都没打开成功过**。
  ⇒ 所以这次**两件事一起做**：文案全部走 `t()`，并且把这一窗加进
    `verify_ui_english` 的清单（否则"翻了"这件事同样没人守）。
  ⚠ 文案必须**直接调 `t(...)`**，不许包一层 `_t = t` 之类的壳 ——
    `tools/i18n_check.py` 是按 `t(` 这个**函数名**找 key 的，包了壳它一个都扫不到，
    于是"漏译"又变成静默的。这个坑很隐蔽：界面看着是翻的，检查却是瞎的。
  ⚠ `（未标：xxx）` 这类**数据层拼出来的标签**也在这里翻，认法用
    `U.UNLABELED_PREFIX`（不写死中文）—— 见 `_disp_agent` 的说明。

· 「×」的位置跟着**各系统的习惯**走（Windows 右上角 / macOS、Linux 左上角），
  与其它对话框（`app_flet.mk_dialog`）一致 —— 用户说的是"右上角"，
  而他在 Windows 上看到的就正是右上角。

· 左栏每个**项目**条目右边一个垃圾桶 ⇒ 删掉该项目在台账里的全部记录。
  ★ 「软件整体」那一条**不给删**：它是汇总，不是一条可删的记录。
  ★ 删之前**必须**走确认框（`_confirm_danger`，与拾卷删存档同一个），
    并且把"删什么、多少条、多少钱、删了不恢复"都列清楚。

English:
**Usage report dialog** (the user's second requirement on 2026-10-10).
Layout (specified by the user item by item, followed here as-is)
------------------------------
    Dialog is maximized by default; **four columns**, left to right:
    | Column 1 | Column 2 | Column 3 | Column 4 |
    |---|---|---|---|
    | Whole app + each project (scrollable if many) | Statistics cards loaded by **partition mode** | Each **Agent** under the current card | **Detailed statistics** (table) |
    · Column 2 partitions: whole app **model / date / module** (3);
      a project **model / date / simulation task / module** (4).
★★ 2026-10-11: **Filters changed from "a single row at the top" to "each column's own header"**
----------------------------------------------------------
User's exact words: "About usage - the UI design is problematic, those filter functions you have
at the top now, I want it so that except for the leftmost column,
the middle second and third columns each have their own set of filters, and put them on **each
column's header** using an appropriate **context menu**,
instead of putting them in a separate place." - After asking, the user chose: **Column 3 hosts
both menus**
(time range + Agent filter); Column 4 (detail table) does **not** get header filters.
So:
| Column | Header (fixed **outside the scroll area**) | Menu |
|---|---|---|
| 1 | Scope · whole app + each project | None (the user explicitly said "except the leftmost column") |
| 2 | Partition · `model ▾` | That column's partition mode (3 / 4 items, changes with scope) |
| 3 | Agent · `🗓` `☰` | **Time range** + **Agent filter** (both menus go in this column) |
| 4 | Detail · current path | None |
· Menus use `ft.PopupMenuButton` + `ft.PopupMenuItem` (the **context menu** form): the current
item has a check
  (`checked=True`), so "which filter is active now" is **readable** from the menu, not from memory;
  the small text under the header restates it.
· ⚠ Headers are placed **outside the scroll area** - this is exactly what a "header" should do:
content scrolls, filters stay pinned at the top.
· ⚠ **"Time range" applies to all four columns** (`day >= since` is a global window in SQL); it
is placed in Column 3
  **at the user-specified location**, not "only affecting Column 3". Column 3's small text also just says "time range", without a qualifier.
★ Three hard constraints (named by the user + this project's iron rules)
------------------------------------
1. **All numbers are computed directly by the database, no model calls** - there is not a single LLM call in the UI
   (`llm/usage` is pure SQL).
2. **Do not persist to md**: only read the DB, only assemble controls in memory (user: "do not save md and other info locally,
   store statistics in the database by default, and dynamically generate the UI elements using the software when needed").
3. **Bilingual Chinese/English** (added 2026-10-10).
⚠ This module does **not import `gui.app_flet`** (that would be a circular import: app_flet
needs to import it to wire up the entry point).
  Colors are passed in by the caller via the `colors` parameter - `app_flet.C` is that dict.
  ⇒ When helpers from `app_flet` are needed (`mk_icon_btn` / `dialog_close_side`), **keep an equivalent copy in this file**,
    for the same reason as `_pad` / `_border`. Criterion G6 of `verify_usage_stats`
    pins this down.
★★ 2026-10-10 second item: **make the whole window bilingual + top-right "×" + left column
projects deletable**
--------------------------------------------------------------
· This window used to be **hardcoded Chinese throughout** - the **only** window in the product
without bilingual support
  (full of Chinese under the English UI). The root cause is not "forgot to translate", but that **the criteria never opened it**:
  it was not among the 9 dialogs in `verify_ui_english`, and it itself never even opened successfully once because it used
  `ft.padding.all` / `page.open()` which do not exist in Flet 1.0.
  ⇒ So this time **both things are done together**: all strings go through `t()`, and this window is added to the
    `verify_ui_english` list (otherwise "it is translated" is equally unguarded).
  ⚠ Strings must **call `t(...)` directly**, no wrapper shell like `_t = t` -
    `tools/i18n_check.py` finds keys by the **function name** `t(`, and with a wrapper it scans none of them,
    so "missed translations" become silent again. This pitfall is very subtle: the UI looks translated, but the check is blind.
  ⚠ Data-layer-assembled labels like `(unlabeled: xxx)` are also translated here, recognized via
    `U.UNLABELED_PREFIX` (not hardcoded Chinese) - see the note on `_disp_agent`.
· The "×" position follows **each OS's convention** (top-right on Windows / top-left on macOS,
Linux),
  consistent with the other dialogs (`app_flet.mk_dialog`) - the user said "top-right",
  and what he sees on Windows is indeed the top-right.
· Each **project** entry in the left column has a trash can on its right ⇒ deletes all records
of that project in the ledger.
  ★ The "software overall" entry **cannot be deleted**: it is an aggregate, not a deletable record.
  ★ Before deleting, it **must** go through a confirmation dialog (`_confirm_danger`, the same one used for deleting scroll archives),
    and it must clearly list "what is being deleted, how many entries, how much money, and that deletion is irreversible".
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import flet as ft

from export import usage_report as REPORT
from i18n import t
from llm import usage as U
from llm import tokens as TOK

_LOG = logging.getLogger('nws.gui.usage')

#: `_prime_hbars` 的执行留痕 —— **判据用它回答"为什么条没出来"**。
#: 与 `dlg._usage_state` 同一个用意：状态挂出来，判据才不用去猜
#: （"条没出现"可能是没滚成功、也可能是滚动抛了异常，两者在界面上长得一样）。
# [EN] : Trace of `_prime_hbars` runs -- **the checks use it to answer "why didn't the bar appear"**.
# [EN] Same intent as `dlg._usage_state`: expose the state so the checks don't have to guess
# [EN] ("the bar didn't show" could be a failed scroll or an exception; the two look identical on
# [EN] screen).
PRIME_LOG: list = []

# ══════════════════════════════════════════════════════════════════
#  栏头（表头）那几套筛选的取值表 —— **数据在模块级，界面只负责画**
#  ⚠ 下面这些显示名是**动态取值**（`t(名字)`），`tools/i18n_check.py` 扫不到字面量
#    ⇒ 必须手工登记进 `i18n.py`。漏了不会崩，只是英文界面下露中文。
# [EN] Table header (column header) filter value tables -- **data lives at module level, the UI only
# [EN] draws it**
# [EN] ⚠ The display names below take values **dynamically** (`t(name)`), so `tools/i18n_check.py`
# [EN] can't find the literals
# [EN] ⇒ They must be manually registered into `i18n.py`. Missing one won't crash, it'll just leak
# [EN] Chinese in the English UI.
# ══════════════════════════════════════════════════════════════════
#: 第 3 栏「Agent 筛选」的四种预设：`all` 全部 / `crew` 只看有 Agent 名的 /
#: `unknown` 只看"（未标：用途）"那一档 / `major` 只看花费较大的。
#: ⚠ 四项**互斥**（用户要的是"一套筛选"，不是一个多维查询器）——
#:   组合筛选会把栏头变成一个小查询界面，而这一栏只有 150px 宽。
# [EN] : Column 3 "Agent filter" has four presets: `all` everything / `crew` only those with an Agent
# [EN] name /
# [EN] : `unknown` only the "(unlabeled: purpose)" tier / `major` only the larger spenders.
# [EN] : ⚠ The four are **mutually exclusive** (the user wants "one filter set", not a multi-dimension
# [EN] query builder) --
# [EN] : combining filters would turn the column header into a mini query UI, and this column is only
# [EN] 150px wide.
AGENT_FILTERS: tuple[str, ...] = ('all', 'crew', 'unknown', 'major')
_AGENT_FILTER_LABEL = {
    'all': '全部 Agent',
    'crew': '只看剧组 Agent',
    'unknown': '只看未标用途',
    'major': '只看花费较大的',
}
#: `major` 那一档的门槛（¥）。取 0.10：比它小的都是零头，会把真正的开销淹掉。
# [EN] : The threshold (¥) for the `major` tier. Taking 0.10: anything below it is noise and would
# [EN] drown out the real costs.
MAJOR_COST = 0.10

#: 第 3 栏「时间范围」的预设：`(天数, 显示名)`；天数 0 = 不设下限（全部时间）。
#: 它同时也是"最近 N 天"→ 具体日期的算法（`_preset_since`）。
# [EN] : Column 3 "Time range" presets: `(days, display name)`; days 0 = no lower bound (all time).
# [EN] : It is also the "last N days" → concrete date algorithm (`_preset_since`).
SINCE_PRESETS: tuple[tuple[int, str], ...] = (
    (0, '全部时间'), (1, '今天'), (7, '最近 7 天'), (30, '最近 30 天'))
#: 菜单里最多列几个"具体有记录的日期"（再多就该用 Excel 了）。
# [EN] : Max number of "dates that actually have records" listed in the menu (beyond that you should
# [EN] just use Excel).
SINCE_DATES_MAX = 10

#: 四栏栏头的高度（**固定** —— 第 3 栏有两行小字、第 1 栏只有一行，
#: 不固定的话四个栏头的下沿会参差不齐，一眼就看出来）。
# [EN] : Height of the four column headers (**fixed** -- column 3 has two lines of small text, column 1
# [EN] has only one,
# [EN] : otherwise the bottom edges of the four headers would be ragged, obvious at a glance).
HEAD_TITLE_H = 22
HEAD_SUB_H = 30

# ══════════════════════════════════════════════════════════════════════
#  四栏宽度（2026-10-11 用户：「第 1 2 3 列适当收窄 第 4 列放大」）
# [EN] Four-column widths (user 2026-10-11: "narrow columns 1 2 3, widen column 4")
# ══════════════════════════════════════════════════════════════════════
#
#  ★★ **改这里之前先看这条**：原来四栏各写了 `width=170/250/150/430`，**但一点用都没有** ——
#     `_pane()` 同时给了 `expand=True`，而 Flet 里 `expand` 会把控件包进 `Expanded`、
#     拿到的是"强制撑满"约束 ⇒ **`width` 被忽略，四栏等宽**。
#     实测（`developers/probe_usage_widths.py`，1920 屏）：四栏都是 **~442px**，
#     和源码里那四个数字毫无关系。所以「第 4 栏放大」这句话在改之前是**做不到**的。
#     ⇒ 现在的分工：**第 1~3 栏固定宽、第 4 栏 `expand=True` 吃掉剩下的全部宽度**。
# [EN] ★★ **Read this before changing it**: the original four columns each had `width=170/250/150/430`,
# [EN] **but it had no effect at all** --
# [EN] `_pane()` also passed `expand=True`, and in Flet `expand` wraps the control in `Expanded`,
# [EN] which applies a "force fill" constraint ⇒ **`width` is ignored, and the four columns are equal
# [EN] width**.
# [EN] Measured (`developers/probe_usage_widths.py`, 1920 screen): all four columns are **~442px**,
# [EN] having nothing to do with those four numbers in the source. So "enlarge column 4" was
# [EN] **impossible** before the change.
# [EN] ⇒ Current split: **columns 1~3 have fixed width, column 4 uses `expand=True` to take all
# [EN] remaining width**.
#
#  ★ 为什么第 4 栏不写宽度：窗口多大它就该多大。写死就没法"尽量显示所有信息"了。
#  ★ 宽度是按**内容**定的（不是随手缩）：
#      · 第 1 栏（范围）：项目名 + 垃圾桶按钮（26px）+ 行内边距 20；
#        名字单行显示，150 能装下 6~7 个汉字；
#      · 第 2 栏（划分）：卡片标题与被选中份额同行 + 第二行「12 次 · 15.4K · ¥0.20」，
#        那行小字约 175px，加卡片内边距 14 ⇒ 200 合适；
#      · 第 3 栏（Agent）：名字最多两行 + 「3 次 · ¥0.23」约 85px ⇒ 130 够。
# [EN] ★★ **Before changing anything here, read this**: the four columns used to declare
# [EN] `width=170/250/150/430`, **which did nothing at all** -- `_pane()` also passed `expand=True`, and
# [EN] in Flet `expand` wraps the control in an `Expanded`, which receives "forced to fill" constraints
# [EN] ⇒ **`width` is ignored and all four columns end up equal**. Measured
# [EN] (`developers/probe_usage_widths.py`, 1920 screen): all four were **~442px**, with no relation to
# [EN] those four numbers in the source. So "widen column 4" was **impossible** before this change.
# [EN] ⇒ The division of labour now: **columns 1-3 have fixed widths, column 4 uses `expand=True` and
# [EN] eats all the remaining width**.
# [EN] ★ Why column 4 has no width: it should be as wide as the window is. Hardcoding it would make
# [EN] "show as much information as possible" impossible.
# [EN] ★ The widths are derived from **content** (not narrowed arbitrarily):
# [EN] · Column 1 (scope): project name + trash button (26px) + row padding 20; the name shows on one
# [EN] line, and 150 fits 6-7 Han characters;
# [EN] · Column 2 (division): card title shares a row with the selected share + a second line
# [EN] "12 times · 15.4K · ¥0.20" which is ~175px, plus card padding 14 ⇒ 200 fits;
# [EN] · Column 3 (Agent): the name may take two lines + "3 times · ¥0.23" at ~85px ⇒ 130 is enough.
PANE_W = {1: 150, 2: 200, 3: 130}
#: 栏间距（`ft.Row(spacing=…)`），算"第 4 栏能拿多少"时要减掉。
# [EN] : gap between columns (`ft.Row(spacing=...)`), subtracted when computing "how much column 4
# [EN] gets".
PANE_GAP = 6

#: 对话框相对窗口**每边**留的边距（用户 2026-10-11：「整体 LLM 窗口默认最大化」）。
#: ⚠ 为什么不是"真正铺满"（0）：无模态对话框贴着窗口边缘时**看不出它是个对话框**，
#:   连"这是浮层、关掉就回到主界面"这件事都读不出来。留 12px 既等于最大化，又留住了边框。
# [EN] : margin the dialog leaves on **each side** of the window (user 2026-10-11: "make the whole LLM
# [EN] window maximized by default").
# [EN] ⚠ Why not "truly flush" (0): a modeless dialog pressed against the window edges **doesn't read
# [EN] as a dialog** -- you can't even tell "this is an overlay, closing it returns to the main screen".
# [EN] 12px is effectively maximized while keeping the frame readable.
DLG_MARGIN = 12
#: 屏幕特别小的时候的兜底尺寸（与原来一致，别在窄屏上把对话框压成一条）。
# [EN] : fallback size for very small screens (unchanged, so the dialog isn't squashed into a strip on a
# [EN] narrow screen).
DLG_MIN_W = 760
DLG_MIN_H = 480

#: 兜底配色（调用方没给 `colors` 时用）。取的是中性色，浅色主题下可读。
#: ⚠ `seal`（朱砂）必须在这儿有一份：删除按钮要用它，
#:   少了的话 `_c()` 会回退成灰 —— "危险按钮不是红的"是最容易被忽略的一种错。
# [EN] : Fallback colors (used when the caller doesn't pass `colors`). Neutral colors, readable on
# [EN] light themes.
# [EN] : ⚠ `seal` (cinnabar) must be present here: the delete button needs it,
# [EN] : without it `_c()` falls back to gray -- "the danger button isn't red" is the easiest kind of
# [EN] bug to overlook.
_FALLBACK = {'card': '#fdfaf2', 'border': '#d8cfbe', 'muted': '#7a7266',
             'ink': '#2b2620', 'gold': '#8a6d3b', 'paper_hi': '#ffffff',
             'seal': '#c02c22'}


def _c(colors: dict | None, key: str) -> str:
    d = colors if isinstance(colors, dict) else _FALLBACK
    return str(d.get(key) or _FALLBACK.get(key) or '#888888')


# ══════════════════════════════════════════════════════════════
#  ★★★ 三个"Flet 1.0 兼容"的小助手 —— **这个文件原来直接用了不存在的 API**
#  （2026-10-10，用户报"网址对话框太高"时顺着查出来的：
#   `ft.padding.all` / `ft.padding.symmetric` / `ft.border.all` 在 **Flet 1.0.3 里
#   都不存在**（`ft.padding` 那个模块只有 `Padding` 类，没有这几个便捷函数）。
#   ⇒ 后果：「用量统计」这个对话框**一次都没打开成功过** —— 点一下抛
# [EN] ★★★ Three "Flet 1.0 compatibility" helpers -- **this file originally used APIs that don't
# [EN] exist**
# [EN] (2026-10-10, traced while investigating the user's report that "the URL dialog is too tall":
# [EN] `ft.padding.all` / `ft.padding.symmetric` / `ft.border.all` **do not exist in Flet 1.0.3**
# [EN] (the `ft.padding` module only has the `Padding` class, not these convenience functions).
# [EN] ⇒ Consequence: the "Usage Statistics" dialog **never once opened successfully** -- clicking it
# [EN] throws
#     `AttributeError: module 'flet.controls.padding' has no attribute 'all'`；
#     而 `app_flet.show_usage_dialog` 的 except 里又写了一个**本文件不存在的**
#     `_LOG` ⇒ **真错误被 `NameError` 顶掉**，用户看到的是"点了没反应"。
#   ⇒ 判据 `tools/verify_ft_api.py` 现在会把这类"不存在的 Flet 属性"一次全报出来
#     （逐段 `getattr` 真的 Flet；静态、毫秒级、不起窗口）。
#  ⚠ 本文件在 `gui/` 下，但**不能** import `app_flet` 的 `make_border`（循环导入）
#    ⇒ 这里各留一份等价的。
# [EN] and the except branch of `app_flet.show_usage_dialog` refers to a `_LOG` **that doesn't exist in
# [EN] this file**
# [EN] ⇒ **the real error gets masked by a `NameError`**, so what the user sees is "clicked and nothing
# [EN] happened".
# [EN] ⇒ The `tools/verify_ft_api.py` check now reports all such "non-existent Flet attributes" in one
# [EN] pass
# [EN] (section by section, `getattr` on the real Flet; static, millisecond-scale, no window).
# [EN] ⚠ This file is under `gui/`, but must **not** import `app_flet`'s `make_border` (circular
# [EN] import)
# [EN] ⇒ Keep an equivalent copy of each here.
# ══════════════════════════════════════════════════════════════
def _pad(v: int = 0, h: int = 0) -> ft.Padding:
    """`ft.padding.symmetric(vertical=v, horizontal=h)` 的等价物。
        English:
    The equivalent of `ft.padding.symmetric(vertical=v, horizontal=h)`.
    """
    return ft.Padding(left=h, top=v, right=h, bottom=v)


def _pad_all(n: int) -> ft.Padding:
    """`ft.padding.all(n)` 的等价物。
        English:
    The equivalent of `ft.padding.all(n)`.
    """
    return ft.Padding(left=n, top=n, right=n, bottom=n)


def _border(width: int = 1, color: str = '#888888') -> ft.Border:
    """`ft.border.all(width, color)` 的等价物（四边同一条边）。
        English:
    The equivalent of `ft.border.all(width, color)` (same border on all four sides).
    """
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, bottom=side, left=side, right=side)


def _icon_btn(icon, on_click, *, colors: dict | None = None, size: int = 26,
              height: int = 22, danger: bool = False,
              tooltip: str = '') -> ft.Container:
    """图标小按钮 —— **与 `app_flet.mk_icon_btn` 等价**（不能 import，见文件头）。

    ⚠ 别用 `ft.IconButton`：它自带 40~48px 的内边距，会把标题行顶得很高。
    ⚠ 里面那个 `ft.Icon` **不许**再挂 `on_click`（容器已经接了）——
      两层都接的话一次点击会走到两个回调里。
    
        English:
    Small icon button — **equivalent to `app_flet.mk_icon_btn`** (cannot import, see file header).
        ⚠ Do not use `ft.IconButton`: it has built-in 40~48px padding that pushes the title row very tall.
        ⚠ The inner `ft.Icon` **must not** have `on_click` attached again (the container already handles it) —
          if both layers handle it, a single click will go to two callbacks.
    """
    fg = _c(colors, 'paper_hi') if danger else _c(colors, 'ink')
    bg = _c(colors, 'seal') if danger else _c(colors, 'card')
    bd = _c(colors, 'seal') if danger else _c(colors, 'border')
    return ft.Container(
        content=ft.Icon(icon, size=max(10, size - 11), color=fg),
        width=size, height=height, border_radius=4, bgcolor=bg,
        border=_border(1, bd), alignment=ft.Alignment(0, 0),
        on_click=on_click, tooltip=(tooltip or None))


def _close_side() -> str:
    """那个「×」放哪一边 —— 与 `app_flet.dialog_close_side()` 同一套（不能 import）。

    Windows 右上角，macOS / Linux 左上角（用户 2026-10-06 点名）。
    认不出来的平台按 Windows 来（右上角）。
    
        English:
    Which side the "×" goes on — the same scheme as `app_flet.dialog_close_side()` (cannot import).
        Windows top-right, macOS / Linux top-left (user specified on 2026-10-06).
        Unrecognized platforms are treated as Windows (top-right).
    """
    if sys.platform.startswith('win'):
        return 'right'
    if sys.platform in ('darwin', 'linux'):
        return 'left'
    return 'right'


def _preset_since(days: int) -> str:
    """「最近 N 天」→ 一个具体日期（`day >= since` 里的那个 since）。

    `days <= 0` ⇒ `''`（不设下限）；`1` = 今天（只看当天）。
    ⚠ 用**本地日期** —— 台账的 `day` 列写的是 `date.fromtimestamp(ts).isoformat()`，
      两边同一套口径，不然"今天"会差一天。
    
        English:
    "Last N days" → a concrete date (the since in `day >= since`).
        `days <= 0` ⇒ `''` (no lower bound); `1` = today (only the current day).
        ⚠ Use **local date** — the `day` column in the ledger stores `date.fromtimestamp(ts).isoformat()`,
          both sides use the same convention, otherwise "today" will be off by one day.
    """
    if days <= 0:
        return ''
    return (date.today() - timedelta(days=days - 1)).isoformat()


def _money(x: float) -> str:
    return U.fmt_cost(x)


def _tokens(n: int) -> str:
    return U.fmt_tokens(n)


# ══════════════════════════════════════════════════════════════════
def open_usage_dialog(app, *, colors: dict | None = None,
                      path: Path | None = None) -> None:
    """打开用量报表。`app` 是 `NovelWorldApp`（只要它有 `.page`）。

    ★ **每次打开都现读库**（用户要的"实时"）：对话框是**一次性构造**的，
      关掉即释放 —— 不做"常驻监听"。理由：这本账是给人**看**的，
      不是仪表盘；常驻监听要处理并发写与刷新时机，为它引入一整条状态链
      不划算（要看最新的，重新打开一次就行）。
    
        English:
    Open the usage report. `app` is `NovelWorldApp` (it only needs to have `.page`).
        ★ **Read the DB fresh on every open** (the user wants "real-time"): the dialog is **constructed once**,
          freed on close — no "resident listener". Reason: this ledger is for people to **read**,
          not a dashboard; a resident listener would need to handle concurrent writes and refresh timing, and introducing a whole state chain
          for it is not worth it (to see the latest, just reopen it).
    """
    page = getattr(app, 'page', None)
    if page is None:
        return
    if path is None:
        # ⚠ 这里**故意**不走 `default_projects_dir()`：用量是**软件级**的账，
        #   项目根目录换了也不该换库。位置固定 = 软件根目录下的 usage.db。
        # [EN] ⚠ This **deliberately** does not go through `default_projects_dir()`: usage is a
        # [EN] **software-level** account,
        # [EN] changing the project root directory shouldn't change the database. Fixed location = usage.db
        # [EN] under the software root.
        path = U.db_path()

    # ── 状态 ──
    # [EN] -- state --
    st: dict = {'scope': None, 'by': U.BY_MODEL, 'key': '', 'agent': '',
                'since': '', 'agent_kind': 'all', 'lang': 'zh'}

    # ── 四栏容器（每次切换只重建需要重建的那几栏）──
    # [EN] -- four-column containers (each switch only rebuilds the columns that need rebuilding) --
    col1 = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
    col2 = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
    col3 = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
    col4 = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
    #: 四个栏头（"表头"）。它们**不在滚动区里**，内容滚起来它们还钉在顶上。
    # [EN] : Four column headers ("table headers"). They are **not inside the scroll area**, so they stay
    # [EN] pinned to the top while the content scrolls.
    head1, head2, head3, head4 = (ft.Container(), ft.Container(),
                                  ft.Container(), ft.Container())
    tip = ft.Text('', size=11, color=_c(colors, 'muted'))

    # ══ 栏头（表头）与它自己那套筛选 ══════════════════════════════
    #  ★ 用户 2026-10-11：「最上面那几个筛选功能……中间第二个第三个列都有自己的一套筛选，
    #    且用合适的**上下文菜单**的方式放到**每个列的表头上**，而不是单独放一个地方。」
    #    ⇒ 顶上那排「划分 / 自」两个下拉**已经删掉**，改成下面这几个菜单。
    # [EN] ══ Column header (table header) and its own filter set ══════════════════════════════
    # [EN] ★ User 2026-10-11: "Those top filter functions... the middle second and third columns each have
    # [EN] their own filter set,
    # [EN] and they should be placed on **each column's header** via an appropriate **context menu**,
    # [EN] rather than in a separate spot."
    # [EN] ⇒ The two top dropdowns "division / by" have **already been removed**, replaced by the menus
    # [EN] below.
    def _head(title: str, *, menus: list | None = None, subs: tuple = (),
              colors) -> ft.Control:
        """一个栏头：标题（右边可挂菜单） + **固定高度**的小字区。

        ⚠ 高度写死（`HEAD_TITLE_H` + `HEAD_SUB_H`）：第 3 栏有两行小字、
          第 1 栏只有一行 —— 不写死，四个栏头的下沿就参差不齐，一眼看得出来。
        
                English:
        A column header: title (menu can be attached on the right) + **fixed-height** small-text area.
                ⚠ Hardcoded height (`HEAD_TITLE_H` + `HEAD_SUB_H`): column 3 has two lines of small text,
                  column 1 has only one line — without hardcoding, the bottom edges of the four column headers would be uneven, visible at a glance.
        """
        top = ft.Container(
            content=ft.Row(
                [ft.Text(title, size=12, weight=ft.FontWeight.BOLD,
                         color=_c(colors, 'ink'), max_lines=1)]
                + list(menus or []),
                spacing=4, tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=HEAD_TITLE_H)
        sub = ft.Container(
            content=ft.Column(
                [ft.Text(str(s), size=10, color=_c(colors, 'muted'), max_lines=2,
                         overflow=ft.TextOverflow.ELLIPSIS) for s in subs],
                spacing=0, tight=True),
            height=HEAD_SUB_H)
        return ft.Column([top, sub], spacing=0, tight=True)

    def _menu(rows: list[tuple], *, colors, label: str = '', icon=None,
              tooltip: str = '', tag: str = '') -> ft.Control:
        """栏头上的一个**上下文菜单**（点它弹出来）。

        `rows` = `[(文案, 是否当前项, 回调), …]`；文案给 `None` 就画一条分隔线。

        ★ `checked=True` 会在菜单项前面画勾 ⇒「现在是哪一个」在菜单里**读得出来**，
          不用靠记忆（从下拉框换成菜单时最容易丢的就是这个信息）。
        ★ 文案**由调用方翻好**：菜单里还有「具体日期」这种**数据**（`2026-10-11`），
          在 `_menu` 里统一 `t()` 会把数据也送进 i18n 查表。
        
                English:
        A **context menu** on the column header (click it to pop up).
                `rows` = `[(text, is_current, callback), …]`; if the text is `None`, draw a separator line.
                ★ `checked=True` draws a checkmark before the menu item ⇒ "which one is currently selected" is **readable** from the menu,
                  no need to rely on memory (this is the information most easily lost when switching from a dropdown to a menu).
                ★ The text is **translated by the caller**: the menu also contains **data** like "concrete date" (`2026-10-11`),
                  and applying `t()` uniformly in `_menu` would send that data into the i18n lookup table too.
        """
        items: list[ft.Control] = []
        for txt, cur, fn in rows:
            if txt is None:
                items.append(ft.PopupMenuItem(
                    content=ft.Container(height=1, bgcolor=_c(colors, 'border'))))
                continue
            items.append(ft.PopupMenuItem(
                content=ft.Text(str(txt), size=12, color=_c(colors, 'ink')),
                checked=bool(cur), height=32,
                on_click=(lambda f: (lambda e: f() if f else None))(fn)))
        common = dict(items=items, tooltip=(tooltip or None),
                      menu_position=ft.PopupMenuPosition.UNDER,
                      padding=_pad(2, 2))
        if label:
            btn: ft.Control = ft.PopupMenuButton(
                content=ft.Row([ft.Text(label, size=12, color=_c(colors, 'ink'),
                                        max_lines=1),
                                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=16,
                                        color=_c(colors, 'muted'))],
                               spacing=1, tight=True), **common)
        else:
            btn = ft.PopupMenuButton(icon=icon, icon_size=16,
                                     icon_color=_c(colors, 'muted'), **common)
        #: 判据用的抓手 —— 真机脚本靠它认出"哪个菜单是哪一套筛选"
        # [EN] : Handles for the checks -- the on-device script uses them to recognize "which menu is which
        # [EN] filter set"
        btn._usage_menu = tag
        return btn

    def _by_list() -> tuple[str, ...]:
        """第 2 栏能用的划分方式（软件整体 3 个 / 项目 4 个 —— 用户点名的区别）。
                English:
        Available partition methods for column 2 (3 for software overall / 4 for project — the
        difference specified by the user).
        """
        bys = U.BY_FOR_PROJECT if st['scope'] else U.BY_FOR_GLOBAL
        return bys

    def _since_text() -> str:
        """时间范围的显示名（预设用名字；具体日期**原样**显示 —— 它是数据）。
                English:
        Display name of the time range (presets use the name; concrete dates are displayed **as-is** —
        they are data).
        """
        s = str(st['since'] or '')
        if not s:
            return t('全部时间')
        for days, name in SINCE_PRESETS:
            if days and _preset_since(days) == s:
                return t(name)
        return s

    def _agent_text() -> str:
        """Agent 筛选的显示名。
                English:
        Display name of the Agent filter.
        """
        k = st['agent_kind']
        return t(_AGENT_FILTER_LABEL.get(k, _AGENT_FILTER_LABEL['all']))

    def _path_text() -> str:
        """第 4 栏栏头那行小字：现在看的是哪一块（原来写在第 4 栏内容顶上）。
                English:
        The small text line in the column 4 header: which block is currently being viewed (previously
        written at the top of column 4's content).
        """
        s = st['scope'] or t('软件整体')
        if st['key']:
            s += ' · ' + t('{by}：{key}', by=t(st['by']), key=_disp_group(st['key']))
        if st['agent']:
            s += ' · ' + _disp_agent(st['agent'])
        return s

    def _by_rows() -> list[tuple]:
        return [(t(b), st['by'] == b,
                 (lambda bb: (lambda: _set_by(bb)))(b)) for b in _by_list()]

    def _since_rows() -> list[tuple]:
        rows: list[tuple] = [
            (t(name), st['since'] == _preset_since(days),
             (lambda dd: (lambda: _set_since(_preset_since(dd))))(days))
            for days, name in SINCE_PRESETS]
        ds = U.recent_days(60, path=path)
        if ds:
            rows.append((None, False, None))                     # 分隔线
            # [EN] Divider
            for d in reversed(ds[-SINCE_DATES_MAX:]):
                rows.append((d, st['since'] == d,
                             (lambda dd: (lambda: _set_since(dd)))(d)))
        return rows

    def _agent_rows() -> list[tuple]:
        return [(t(_AGENT_FILTER_LABEL[k]), st['agent_kind'] == k,
                 (lambda kk: (lambda: _set_agent_kind(kk)))(k))
                for k in AGENT_FILTERS]

    def _disp_agent(key: str) -> str:
        """第三层的 key → 给人看的字。

        ★ `（未标：xxx）` 是**数据层拼出来的**（见 `llm/usage.agents` 的 SQL），
          而且它是**不透明的 key**：点它的时候会**原样**回传给 `detail()` 当过滤条件
          （那边靠 `startswith(UNLABELED_PREFIX)` 认出来）。
          ⇒ 所以这里只翻**显示**的那一份，绝不改动那个值本身。
          认法用 `U.UNLABELED_PREFIX`（**不写死中文**）：界面和 SQL 认的是同一个常量，
          改了前缀也不会出现"点得进去、查不出东西"。

        ★ Agent 名走 `t()`：那些名字（小说作家 / 剧作者 / 场记…）是**本软件的词汇**
          （库存在 i18n 里、剧组界面上也是翻的），不翻的话英文界面下这一栏全是中文。
          ⚠ 但 `（未标：xxx）` 里的 `purpose` 是**值**（`crew_novelist` 这种），不翻。
          ⚠ 与「划分」的值（模型名 / 日期 / 模块 / 存档名）**刻意不同**：那些是数据，
            一律原样显示 —— 翻数据会让界面和盘上的东西对不上。
        
                English:
        Third-level key → the human-readable text.
                ★ `(unlabeled: xxx)` is **assembled by the data layer** (see the SQL in `llm/usage.agents`),
                  and it is an **opaque key**: when clicked it is passed back **as-is** to `detail()` as a filter condition
                  (that side recognizes it via `startswith(UNLABELED_PREFIX)`).
                  ⇒ so here only the **display** copy is translated, and that value itself is never modified.
                  Recognition uses `U.UNLABELED_PREFIX` (**do not hardcode Chinese**): the UI and the SQL recognize the same constant,
                  so even if the prefix changes, there will be no "clickable but returns nothing" situation.
                ★ Agent names go through `t()`: those names (novelist / screenwriter / script supervisor…) are **vocabulary of this software**
                  (the inventory is in i18n, and the crew UI is also translated), otherwise in the English UI this column would be all Chinese.
                  ⚠ But the `purpose` inside `(unlabeled: xxx)` is a **value** (like `crew_novelist`), do not translate.
                  ⚠ It is **deliberately different** from the values of "partition" (model name / date / module / archive name): those are data,
                    and are always displayed as-is — translating data would make the UI mismatch what is on disk.
        """
        k = str(key or '')
        if k.startswith(U.UNLABELED_PREFIX) and k.endswith('）'):
            return t('（未标：{p}）', p=k[len(U.UNLABELED_PREFIX):-1])
        return t(k) if k else t('（未标）')

    def _disp_group(key: str) -> str:
        """第二层卡片的 key → 给人看的字（空的那些由数据层填成「未标」）。
                English:
        Layer 2 card key → human-readable label (empty ones are filled in by the data layer as "未标").
        """
        return t('（未标）') if str(key) == U.UNLABELED else str(key)

    def _btn(label: str, fn, **kw) -> ft.Control:
        return ft.TextButton(content=ft.Text(label, size=12), on_click=fn, **kw)

    # ── 第 1 栏：软件整体 + 项目 ──
    # [EN] -- Column 1: whole-software + projects --
    def build_col1() -> None:
        col1.controls.clear()
        g = U.totals(None, since=st['since'] or None, path=path)
        col1.controls.append(_nav_row(
            t('软件整体'), t('{n} 次 · {c}', n=g['calls'], c=_money(g['cost'])),
            active=(st['scope'] is None),
            on_click=lambda e: _pick_scope(None), colors=colors))
        col1.controls.append(ft.Divider(height=1, color=_c(colors, 'border')))
        rows = U.projects(path=path)
        if not rows:
            col1.controls.append(ft.Text(t('（还没有记录）'), size=12,
                                        color=_c(colors, 'muted')))
        for r in rows:
            col1.controls.append(_nav_row(
                r['name'], t('{n} 次 · {c}', n=r['calls'], c=_money(r['cost'])),
                active=(st['scope'] == r['name']),
                on_click=(lambda nm: (lambda e: _pick_scope(nm)))(r['name']),
                # ★ 只有**项目**那一条可删；「软件整体」是汇总，不给删（传 None）。
                # [EN] ★ Only the **project** entry is deletable; "whole software" is a summary and isn't deletable
                # [EN] (pass None).
                on_delete=(lambda nm, rr: (lambda: _ask_delete(
                    nm, int(rr['calls']), float(rr['cost']))))(r['name'], r),
                colors=colors))

    def _nav_row(name: str, sub: str, *, active: bool, on_click, colors,
                 on_delete=None) -> ft.Control:
        """左栏的一行。`on_delete` 给了才会出现垃圾桶（「软件整体」不给）。

        ★ 结构上刻意让"可点的那块"和"垃圾桶"做**兄弟**，不是把垃圾桶塞进可点区域里：
          · 兄弟关系 ⇒ 点垃圾桶**不会**顺带把这一项选上（嵌套的点击冒泡在
            Flet / Flutter 里是"最内层接走"，但本项目既有写法就是兄弟，
            跟着它走不会被将来的版本差异咬到）；
          · 拾卷那几张卡片（`_build_novel_card`）也是同一个结构：
            `Row([可点的主体(expand=True), 图标按钮])` —— 主体 `expand` 才把按钮挤到最右。
        
                English:
        A row in the left column. The trash can only appears if `on_delete` is provided ("软件整体" does not
        provide it).
                ★ Structurally, deliberately make the "clickable block" and the "trash can" **siblings**, rather than stuffing the trash can inside the clickable area:
                  · Sibling relationship ⇒ clicking the trash can will **not** also select this item (nested click bubbling in
                    Flet / Flutter is "innermost takes it first", but the existing style in this project is siblings,
                    following it won't get bitten by future version differences);
                  · The card-collecting cards (`_build_novel_card`) use the same structure:
                    `Row([clickable body(expand=True), icon button])` —— only when the body has `expand` is the button pushed to the far right.
        """
        body = ft.Container(
            content=ft.Column([
                ft.Text(name, size=13, weight=ft.FontWeight.BOLD if active else None,
                        color=_c(colors, 'ink'), max_lines=1),
                ft.Text(sub, size=11, color=_c(colors, 'muted')),
            ], spacing=1),
            padding=_pad(4, 4),
            border_radius=6,
            on_click=on_click,
            ink=True,
            expand=True,
        )
        if on_delete is None:
            content: ft.Control = body
        else:
            del_btn = _icon_btn(ft.Icons.DELETE_OUTLINE, on_click=lambda e: on_delete(),
                                colors=colors, danger=True,
                                tooltip=t('删除这个项目的用量记录'))
            #: 判据用的抓手（与 `card._proj` 同一个用意）—— 让"哪一项可删"是**读得出来**的
            # [EN] : Handles for the checks (same intent as `card._proj`) -- make "which entry is deletable"
            # [EN] **readable**
            del_btn._del_scope = name
            content = ft.Row([body, del_btn], spacing=4,
                             vertical_alignment=ft.CrossAxisAlignment.CENTER)
        return ft.Container(
            content=content,
            padding=_pad(6, 8),
            border_radius=6,
            bgcolor=(_c(colors, 'card') if active else None))

    # ── 第 2 栏：划分方式 + 统计卡片 ──
    # [EN] -- Column 2: division method + stat cards --
    def build_col2() -> None:
        col2.controls.clear()
        gs = U.groups(st['scope'], st['by'], since=st['since'] or None, path=path)
        tot = U.totals(st['scope'], since=st['since'] or None, path=path)['cost'] or 0
        if not gs:
            col2.controls.append(ft.Text(t('（这项还没有记录）'), size=12,
                                        color=_c(colors, 'muted')))
        for g in gs:
            share = (g['cost'] / tot) if tot else 0
            _sub = t('{n} 次 · {tok} · {c}', n=g['calls'],
                     tok=_tokens(g['in_tok'] + g['out_tok']), c=_money(g['cost']))
            # ★ 按**模型**分组时，多带一句缓存命中率（2026-10-12）：
            #   "这个模型花了多少钱"要和"它的缓存有没有生效"一起看 —— 命中率高说明
            #   前缀稳定、钱花得值；命中率长期是 0 则说明提示词前缀里混进了变化的东西
            #   （那是"账单翻倍但看不出原因"的经典成因）。
            # [EN] ★ When grouping **by model**, add a cache hit ratio (2026-10-12): "how much this
            # [EN] model cost" should be read together with "is caching working" -- a high ratio means
            # [EN] the prefix is stable and the money is well spent, while a ratio stuck at 0 means
            # [EN] something varying snuck into the prompt prefix (the classic cause of "the bill
            # [EN] doubled and nothing explains why").
            _ct = int(g.get('cache_tok') or 0)
            if st['by'] == U.BY_MODEL and _ct > 0:
                _r = TOK.hit_ratio(int(g.get('in_tok') or 0), _ct)
                _sub += t(' · 缓存命中 {p}', p=f'{_r:.0%}')
            col2.controls.append(_card(
                _disp_group(g['key']), _sub,
                share=f'{share:.0%}',
                active=(st['key'] == g['key']),
                on_click=(lambda k: (lambda e: _pick_key(k)))(g['key']),
                colors=colors))

    def _card(title: str, sub: str, *, share: str, active: bool, on_click,
              colors) -> ft.Control:
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Text(title, size=13, max_lines=1, expand=True,
                                color=_c(colors, 'ink'),
                                weight=ft.FontWeight.BOLD if active else None),
                        ft.Text(share, size=12, color=_c(colors, 'gold'))],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text(sub, size=11, color=_c(colors, 'muted')),
            ], spacing=2),
            padding=_pad(7, 9),
            border=_border(1, _c(colors, 'gold') if active else _c(colors, 'border')),
            border_radius=7,
            bgcolor=(_c(colors, 'card') if active else None),
            on_click=on_click, ink=True)

    # ── 第 3 栏：Agent ──
    # [EN] -- Column 3: Agent --
    def _apply_agent_filter(rows: list[dict]) -> list[dict]:
        """第 3 栏**自己那套筛选**（用户点名这一栏要有）。

        ⚠ 它只改"第 3 栏显示哪些行"。第 4 栏是"选中某个 Agent 之后的明细"，
          走的是 `st['agent']` → SQL，与这里的过滤是两件事（别混）。
        ⚠ 过滤完可能**一个都不剩**（比如这一栏全是"（未标：…）"却选了"只看剧组 Agent"）
          —— 那种时候要出空态文案，不能什么都不画（"一片空白"看着像坏了）。
        
                English:
        Column 3's **own set of filters** (the user specifically named this column as needing them).
                ⚠ It only changes "which rows are shown in column 3". Column 4 is "details after selecting an Agent",
                  going through `st['agent']` → SQL, which is a separate matter from the filtering here (don't mix them up).
                ⚠ After filtering there may be **nothing left at all** (e.g. this column is all "(未标: …)" but you chose "only show 剧组 Agent")
                  —— in that case you must show empty-state text, you can't just draw nothing ("a blank area" looks broken).
        """
        k = st['agent_kind']
        if k == 'crew':
            return [a for a in rows
                    if not str(a['agent']).startswith(U.UNLABELED_PREFIX)]
        if k == 'unknown':
            return [a for a in rows
                    if str(a['agent']).startswith(U.UNLABELED_PREFIX)]
        if k == 'major':
            return [a for a in rows if float(a['cost'] or 0) >= MAJOR_COST]
        return rows

    def build_col3() -> None:
        col3.controls.clear()
        if not st['key']:
            col3.controls.append(ft.Text(t('← 先选一张卡片'), size=12,
                                        color=_c(colors, 'muted')))
            return
        rows = _apply_agent_filter(U.agents(st['scope'], st['by'], st['key'],
                                           since=st['since'] or None, path=path))
        if not rows:
            col3.controls.append(ft.Text(t('（没有明细）'), size=12,
                                        color=_c(colors, 'muted')))
        for a in rows:
            active = st['agent'] == a['agent']
            col3.controls.append(ft.Container(
                content=ft.Column([
                    ft.Text(_disp_agent(a['agent']), size=12, max_lines=2,
                            color=_c(colors, 'ink'),
                            weight=ft.FontWeight.BOLD if active else None),
                    ft.Text(t('{n} 次 · {c}', n=a['calls'], c=_money(a['cost'])),
                            size=10, color=_c(colors, 'muted')),
                ], spacing=1),
                padding=_pad(5, 7),
                border_radius=6,
                bgcolor=(_c(colors, 'card') if active else None),
                # ⚠ 传的是**原样的 key**（不是翻译过的显示字）—— `detail()` 靠它过滤
                # [EN] ⚠ What is passed is the **raw key** (not the translated display text) -- `detail()` filters by
                # [EN] it
                on_click=(lambda an: (lambda e: _pick_agent(an)))(a['agent']),
                ink=True))

    # ── 第 4 栏：明细 ──
    # [EN] -- Column 4: details --
    def build_col4() -> None:
        """重建第 4 栏 —— **唯一入口**（`_build_col4` 只管画，这里补上"重建后的收尾"）。

        ★★ 为什么要包一层：`_prime_hbars()` 必须在**每一次**第 4 栏重建之后跑，
          否则"点进某个 Agent 之后新生成的那根横条"没人去量它、就一直不显示。
          第一版把 `_prime_hbars()` 只挂在 `refresh_all()` 上 —— 而
          `_pick_key` / `_pick_agent` / `_set_by` 三处是**直接调 `build_col4()`** 的，
          于是那条路完全没有量（实测：`PRIME_LOG` 一条都没有，B1b 当场红）。
          ⇒ 收成一个 choke point，将来新加调用点也不会漏。

            English:
        Rebuild column 4 -- **the single entry point** (`_build_col4` only draws; this adds the
        "post-rebuild wrap-up").
                ★★ Why the wrapper: `_prime_hbars()` must run after **every** rebuild of column 4,
                  otherwise "the newly created bar after clicking into an Agent" is never measured and
                  never shows. The first version hung `_prime_hbars()` only on `refresh_all()` -- while
                  `_pick_key` / `_pick_agent` / `_set_by` call `build_col4()` **directly**, so that path
                  never measured at all (measured: not a single `PRIME_LOG` entry; B1b went red on the
                  spot).
                  ⇒ Collapse it into one choke point so future call sites can't miss it.
        """
        # 这一栏要重建 ⇒ 旧的滚动区已经不在树上了，先清掉登记（否则越积越多）
        # [EN] This column is being rebuilt ⇒ the old scroll area is no longer in the tree; clear the
        # [EN] registry first (otherwise it grows without bound)
        hbars.clear()
        _build_col4()
        _prime_hbars()

    def _build_col4() -> None:
        col4.controls.clear()
        # ★ 原来这里有一枚 14 号大字标题（「甲项目 · 模型：xxx · 小说作家」）——
        #   2026-10-11 挪进了**第 4 栏栏头的小字**（`_path_text`）：
        #   栏头是钉住的，而那行标题会跟着内容一起滚走，本来就别扭。
        # [EN] ★ There used to be a size-14 large heading here ("Project A · Model: xxx · Novel Writer") --
        # [EN] on 2026-10-11 it was moved into the **small text of column 4's header** (`_path_text`):
        # [EN] the header is pinned, while that heading scrolled away with the content, which was awkward to
        # [EN] begin with.
        if not (st['key'] or st['agent']):
            g = U.totals(st['scope'], since=st['since'] or None, path=path)
            # ★ 缓存那两行（2026-10-12）：**按模型分别算**省下的钱 —— 单价逐家不同，
            #   拿一个平均价去乘总命中量会算出一个"看着像样、其实不对"的数。
            # [EN] ★ The two cache rows (2026-10-12): the saving is computed **per model** -- unit
            # [EN] prices differ by provider, and multiplying total hits by an average price would
            # [EN] produce a number that "looks plausible but is wrong".
            _saved = 0.0
            _with_cache = 0
            try:
                for _r in U.groups(st['scope'], U.BY_MODEL,
                                   since=st['since'] or None, path=path):
                    if int(_r.get('cache_tok') or 0) > 0:
                        _with_cache += 1
                    _saved += TOK.saved_by_cache(str(_r.get('key') or ''),
                                                 int(_r.get('cache_tok') or 0))
            except Exception:                                    # noqa: BLE001
                _saved = 0.0
            # ⚠⚠ 缓存那两项**并进现有行，不新开行**（2026-10-12 实测的坑）：
            #   第 4 栏**没有纵向滚动**（`_pane()` 里是一个普通 Column），
            #   多两行就把底部的横向滚动条**挤出可视区** ——
            #   `verify_usage_layout` 的 B4b（像素取证）当场红：条量不到颜色，
            #   用户也就真的看不见那根条。
            #   并进「合计 Token」与「费用」之后：**信息一样全，高度一行不涨**。
            # [EN] ⚠⚠ The two cache metrics are **merged into existing rows, no new rows** (a pit
            # [EN] measured on 2026-10-12): column 4 has **no vertical scrolling** (a plain Column inside
            # [EN] `_pane()`), so two extra rows push the horizontal scrollbar at the bottom **out of the
            # [EN] visible area** -- criterion B4b of `verify_usage_layout` (pixel forensics) went red on
            # [EN] the spot: the bar's color cannot be measured, and the user genuinely cannot see that
            # [EN] bar either.
            # [EN] Merged into "Total tokens" and "Cost": **the same information, not one row taller**.
            _ct_sum = int(g.get('cache_tok') or 0)
            _tok_val = f"{g['in_tok'] + g['out_tok']:,}"
            if _ct_sum:
                _tok_val += t('（命中缓存 {n}）', n=f'{_ct_sum:,}')
            _cost_val = _money(g['cost'])
            if _saved > 0:
                _cost_val += t('（缓存省下 {c}）', c=_money(_saved))
            col4.controls.append(_kv_table([
                (t('调用次数'), g['calls']),
                (t('输入 Token'), f"{g['in_tok']:,}"),
                (t('输出 Token'), f"{g['out_tok']:,}"),
                (t('合计 Token'), _tok_val),
                (t('费用'), _cost_val),
                (t('涉及模型'), g['models']),
                (t('涉及模块'), g['modules']),
                (t('涉及 Agent'), g['agents']),
                (t('日期范围'), f"{g['first_day']} ~ {g['last_day']}" if g['first_day'] else '—'),
            ], colors=colors))
            if not _with_cache:
                col8 = ft.Text(t('（还没有命中过缓存 —— 见「AI模型配置」页底部的省钱提示）'),
                               size=11, color=_c(colors, 'muted'))
                col4.controls.append(col8)
            return
        rows = U.detail(st['scope'], st['by'], st['key'], st['agent'],
                        since=st['since'] or None, limit=200, path=path)
        if not rows:
            col4.controls.append(ft.Text(t('（没有调用记录）'), size=12,
                                        color=_c(colors, 'muted')))
            return
        import time as _time
        agg = {'calls': len(rows), 'in_tok': 0, 'out_tok': 0, 'cost': 0.0,
               'cache_tok': 0}
        for r in rows:
            agg['in_tok'] += int(r['in_tok'] or 0)
            agg['out_tok'] += int(r['out_tok'] or 0)
            agg['cache_tok'] += int(r.get('cache_tok') or 0)
            agg['cost'] += float(r['cost'] or 0.0)
        # ⚠ 同上：缓存并进现有行（第 4 栏没有纵向滚动，加行会把横条挤出屏幕）。
        # [EN] ⚠ Same as above: the cache metric is merged into an existing row (column 4 has no vertical
        # [EN] scrolling, and an extra row pushes the horizontal bar off screen).
        _agg_tok = f"{agg['in_tok'] + agg['out_tok']:,}"
        if agg['cache_tok']:
            _agg_tok += t('（命中缓存 {n}）', n=f"{agg['cache_tok']:,}")
        col4.controls.append(_kv_table([
            (t('调用次数'), agg['calls']),
            (t('输入 Token'), f"{agg['in_tok']:,}"),
            (t('输出 Token'), f"{agg['out_tok']:,}"),
            (t('合计 Token'), _agg_tok),
            (t('费用'), _money(agg['cost'])),
        ], colors=colors))
        head = [t('时间'), t('模型'), t('用途'), t('模块'), t('Agent'),
                t('入'), t('出'), t('缓存'), t('费用')]
        data = [[_time.strftime('%m-%d %H:%M', _time.localtime(r['ts'])),
                 r['model'], r['purpose'], r['module'],
                 (_disp_agent(r['agent']) if r['agent'] else '—'),
                 f"{int(r['in_tok'] or 0):,}", f"{int(r['out_tok'] or 0):,}",
                 (f"{int(r['cache_tok'] or 0):,}"
                  if int(r.get('cache_tok') or 0) else '—'),
                 f"{float(r['cost'] or 0):.5f}"] for r in rows]
        col4.controls.append(_h_view(_grid(head, data, colors=colors), colors=colors))

    def _kv_table(pairs: list[tuple[str, object]], *, colors) -> ft.Control:
        return ft.DataTable(
            columns=[ft.DataColumn(ft.Text(t('指标'), size=12)),
                     ft.DataColumn(ft.Text(t('值'), size=12))],
            rows=[ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(k), size=12, color=_c(colors, 'muted'))),
                ft.DataCell(ft.Text(str(v), size=12, color=_c(colors, 'ink'))),
            ]) for k, v in pairs],
            column_spacing=26, heading_row_height=30, data_row_min_height=26)

    def _grid(head: list[str], data: list[list], *, colors) -> ft.Control:
        """8 列明细表（宽度够时一次全显示）。
            English:
        The 8-column detail table (shown in full at once when there's enough width).
        """
        return ft.DataTable(
            columns=[ft.DataColumn(ft.Text(h, size=11)) for h in head],
            rows=[ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(c), size=11, color=_c(colors, 'ink')))
                for c in row]) for row in data],
            column_spacing=16, heading_row_height=28, data_row_min_height=24,
            border=_border(1, _c(colors, 'border')))

    def _h_view(content: ft.Control, *, colors) -> ft.Control:
        """横向滚动区 + **自己画的、常驻显示的**横向滚动条。

        用户 2026-10-11：「尽量保证显示所有信息，**如果不行 第4列加横向滚动条**」。
        分工：
          · **先尽量显示**：第 4 栏是"吃掉剩余宽度"的那一栏（`_pane(..., expand=True)`），
            窗口越大它越宽；`DataTable` 保持**自己的固有宽度**（不会被压缩列），
            所以够宽时八列一次全显示；
          · **放不下再滚**：外面套 `ft.Row(scroll=…)`。实测（`developers/probe_table_scroll.py`，
            380px 视口 + 8 列内容）：`max_scroll_extent = 206.8`、`scroll_to(120)` 后
            `pixels = 120` ⇒ **溢出是真的、滚动是真能用**。

        ★★ 为什么**不用**框架那根条（`ScrollMode.ADAPTIVE`）：
          实测过两次（`.venv` 里同一个 Flet 构建）——
            ① `developers/probe_table_scroll.py`：ADAPTIVE→HIDDEN 前后截图**零差异**；
            ② `tools/verify_usage_layout.py` 的 B4 同样零差异。
          也就是说框架**根本不画**一根常驻的横向条（竖向那根的情况不一样，
          见 `mk_scroll_bar` 里的记录）。而用户要的是"**加横向滚动条**"——
          "能滚但看不见条"不算做到。所以这里走本项目的老办法：
          **`HIDDEN` 关掉框架那根，自己画一根**（`mk_scroll_bar` 是竖的，
          横向得单写一份：`left`/`width` 而不是 `top`/`height`）。
        ★ 放得下时**不画**（`max_scroll_extent <= 1` ⇒ `visible = False`），
          与系统滚动条一致；宽窗口下第 4 栏 1294px 装得下 613px 的表，条就不出现。
        ⚠ `DataTable` 的 `border` 留在表上（不是留在 Row 上）—— 否则滚动时
          边框不动、表格在框里滑，看着像没对齐。

            English:
        A horizontal scroll area + **a self-drawn, always-visible** horizontal scrollbar.
        User 2026-10-11: "try to show all the information, **and if that doesn't work add a horizontal
        scrollbar to column 4**".
        Division of labour:
          · **First try to show everything**: column 4 is the "eats the remaining width" column
            (`_pane(..., expand=True)`), so the wider the window the wider it gets; `DataTable` keeps
            **its own intrinsic width** (columns are not compressed), so with enough width all eight
            columns show at once;
          · **Scroll when it doesn't fit**: wrap it in `ft.Row(scroll=...)`. Measured
            (`developers/probe_table_scroll.py`, 380px viewport + 8 columns of content):
            `max_scroll_extent = 206.8`, and after `scroll_to(120)` `pixels = 120` ⇒ **the overflow is
            real and scrolling really works**.
        ★★ Why **not** use the framework's bar (`ScrollMode.ADAPTIVE`):
          Measured twice (same Flet build in `.venv`) --
            (1) `developers/probe_table_scroll.py`: screenshots before/after ADAPTIVE->HIDDEN show
                **zero difference**;
            (2) B4 in `tools/verify_usage_layout.py`: likewise zero difference.
          In other words the framework **does not draw** a persistent horizontal bar at all (the
          vertical case is different, see the note in `mk_scroll_bar`). And the user asked to "**add a
          horizontal scrollbar**" -- "it scrolls but you can't see a bar" doesn't count as done. So this
          follows the project's old approach: **turn the framework bar off with `HIDDEN` and draw one
          ourselves** (`mk_scroll_bar` is vertical, so a horizontal one must be written separately,
          using `left`/`width` instead of `top`/`height`).
        ★ When it fits, **don't draw it** (`max_scroll_extent <= 1` ⇒ `visible = False`), consistent
          with system scrollbars; in a wide window column 4 is 1294px and holds the 613px table, so the
          bar doesn't appear.
        ⚠ The `DataTable`'s `border` stays on the table (not on the Row) —— otherwise the border stays
          put while the table slides inside it, which looks misaligned.
        """
        bar_w = 4
        row = ft.Row([content], spacing=0, scroll=ft.ScrollMode.HIDDEN)
        thumb = ft.Container(
            height=bar_w, width=48, bgcolor=_c(colors, 'muted'),
            border_radius=bar_w // 2, left=0, top=1,
            visible=False,          # 内容放得下时不画（跟系统滚动条一致）
            # [EN] Not drawn when the content fits (consistent with system scrollbars)
        )
        # ⚠ 车道必须**自己有满宽**，否则 `ft.Stack` 会缩成 `thumb` 那么宽、`left` 就失去参照。
        #   手法：先放一条"撑满宽度的隐形 Row"（`Container(expand=True)` 逼它满宽），
        #   `Stack` 的宽度就由它决定（Flutter 里 Stack 尺寸取最大的非定位子项）。
        # [EN] ⚠ The lane must **carry full width itself**, otherwise `ft.Stack` shrinks to the width
        # [EN] of `thumb` and `left` loses its reference. Trick: first place an "invisible Row that
        # [EN] fills the width" (`Container(expand=True)` forces it), which then determines the Stack's
        # [EN] width (in Flutter a Stack sizes to its largest non-positioned child).
        lane = ft.Stack([ft.Row([ft.Container(expand=True)], height=8), thumb], height=8)
        lane._usage_lane = True

        def _on_scroll(e) -> None:
            """按真实的滚动量重画那根条（**不是"接上了就算数"**）。
                English:
            Redraw the bar from the real scroll metrics (**"wired up" is not enough**).
            """
            try:
                px = float(getattr(e, 'pixels', 0) or 0)
                mx = float(getattr(e, 'max_scroll_extent', 0) or 0)
                vp = float(getattr(e, 'viewport_dimension', 0) or 0)
            except (TypeError, ValueError):
                return
            if mx <= 1 or vp <= 0:
                thumb.visible = False
            else:
                w = max(40.0, vp * vp / (vp + mx))
                thumb.width = round(w, 1)
                thumb.left = round((vp - w) * (min(max(px, 0.0), mx) / mx), 1)
                thumb.visible = True
            try:
                thumb.update()
            except Exception:                                # noqa: BLE001
                pass

        row.on_scroll = _on_scroll
        #: 判据用的抓手：`_usage_hscroll` 挂在**真正滚动的那个 Row** 上（明细表在它里面），
        #: `_usage_hbar` 挂在**自己画的那根条**的容器上（"看得见"那半靠它量）。
        # [EN] : Handles for the checks: `_usage_hscroll` goes on **the Row that actually scrolls**
        # [EN] (the detail table is inside it), `_usage_hbar` goes on **the container of the bar we
        # [EN] draw** (the "visible" half is measured through it).
        row._usage_hscroll = True
        thumb._usage_hbar = True
        box = ft.Column([row, lane], spacing=2, tight=True)
        box._usage_hview = True
        # 登记给 `_prime_hbars`（挂载后主动"量"一次，见它的 docstring）
        # [EN] Register it for `_prime_hbars` (measure once after mounting, see its docstring)
        hbars.append(row)
        return box

    # ── 栏头刷新 + 切换动作 ──
    # [EN] -- header refresh + switch actions --
    def build_heads() -> None:
        """重建四个栏头（范围/筛选一变，栏头上的字与小字都要跟着变）。
                English:
        Rebuild the four column headers (when range/filter changes, the text and small text on the
        headers must change accordingly).
        """
        head1.content = _head(t('范围'), subs=(t('软件整体 + 各项目'),), colors=colors)
        head2.content = _head(
            t('划分'),
            menus=[_menu(_by_rows(), colors=colors, label=t(st['by']),
                         tooltip=t('这一栏按什么分组'), tag='by')],
            subs=(t('按它把这一栏分组'),), colors=colors)
        head3.content = _head(
            t('Agent'),
            menus=[_menu(_since_rows(), colors=colors, icon=ft.Icons.CALENDAR_MONTH,
                         tooltip=t('时间范围（作用于四栏）：{v}', v=_since_text()),
                         tag='since'),
                   _menu(_agent_rows(), colors=colors, icon=ft.Icons.FILTER_ALT,
                         tooltip=t('筛选这一栏的 Agent：{v}', v=_agent_text()),
                         tag='agent')],
            subs=(t('时间：{v}', v=_since_text()),
                  t('筛选：{v}', v=_agent_text())), colors=colors)
        head4.content = _head(t('明细'), subs=(_path_text(),), colors=colors)

    def _pick_scope(scope: str | None) -> None:
        st['scope'] = scope
        st['by'] = (U.BY_FOR_PROJECT if scope else U.BY_FOR_GLOBAL)[0]
        st['key'] = ''
        st['agent'] = ''
        refresh_all()

    def _pick_key(key: str) -> None:
        st['key'] = key
        st['agent'] = ''
        build_heads()
        build_col3()
        build_col4()
        page.update()

    def _pick_agent(agent: str) -> None:
        st['agent'] = '' if st['agent'] == agent else agent
        build_heads()
        build_col3()
        build_col4()
        page.update()

    def _set_by(by: str) -> None:
        """第 2 栏栏头那个菜单选的划分方式。
                English:
        The division method selected by the menu in the column 2 header.
        """
        st['by'] = by or st['by']
        st['key'] = ''
        st['agent'] = ''
        build_heads()
        build_col2()
        build_col3()
        build_col4()
        page.update()

    def _set_since(since: str) -> None:
        """第 3 栏栏头「时间范围」菜单。⚠ 它是**全局窗口**，四栏一起变。
                English:
        The "time range" menu in the column 3 header. ⚠ It is a **global window**, all four columns
        change together.
        """
        st['since'] = str(since or '')
        st['agent'] = ''
        refresh_all()

    def _set_agent_kind(kind: str) -> None:
        """第 3 栏栏头「Agent 筛选」菜单（只影响第 3 栏显示哪些行）。
                English:
        The "Agent filter" menu in the column 3 header (only affects which rows are shown in column 3).
        """
        st['agent_kind'] = kind or 'all'
        st['agent'] = ''
        build_heads()
        build_col3()
        build_col4()
        page.update()

    #: 每次重建第 4 栏时登记下来的横向滚动区（给"开局先量一次"用，见 `_prime_hbars`）。
    # [EN] : Horizontal scroll areas registered each time column 4 is rebuilt (used by
    # [EN] `_prime_hbars` for "measure once up front").
    hbars: list = []

    def _prime_hbars() -> None:
        """挂载后主动给每根横条**一次"测量"用的滚动事件**。

        ★★ 为什么非有它：那根条是靠 `on_scroll` 里的 `max_scroll_extent` 决定
          "画不画、画多长"的，而 `on_scroll` **只在真的滚过一次之后**才触发。
          没有这一步，用户打开对话框时**明明装不下、却看不到条** ——
          非要先滚一下条才冒出来，而"没有条"恰恰会让人以为"不用滚"。
          （这正是用户要的"如果不行 第4列加横向滚动条"没被满足的样子。）
        ★ 手法：滚 1px 再滚回 0。**必须真的动一下**（滚到当前值不会触发事件），
          而且**最后要回到 0**，否则第 4 栏一打开就是偏的。
        ⚠ 用 `page.run_task` 而不是 `asyncio.ensure_future`：前者挂在页面的事件循环上、
          随页面一起收，后者在这个 Flet 构建里会抛"没有运行中的 loop"。
        ⚠ 整个过程**失败也不报错**（`try/except` 吞掉）：它只是"让条更早出现"，
          失败时退化成"滚一下才出现"，不该把对话框本身弄崩。

        English:
        After mounting, actively give each horizontal bar **one "measurement" scroll event**.
        ★★ Why it's mandatory: the bar decides "whether to draw and how long" from
        `max_scroll_extent` inside `on_scroll`, and `on_scroll` **only fires after a real scroll**.
        Without this step the user opens the dialog and **can't see a bar even though it doesn't fit**
        -- they'd have to scroll once first for it to appear, and "no bar" is exactly what makes people
        think "no scrolling needed". (This is precisely what "if it doesn't work, add a horizontal
        scrollbar to column 4" being unmet looks like.)
        ★ Method: scroll 1px then back to 0. It **must really move** (scrolling to the current value
        fires nothing), and it **must end at 0**, otherwise column 4 opens already offset.
        ⚠ Use `page.run_task` rather than `asyncio.ensure_future`: the former hangs on the page's event
        loop and is collected with the page, while the latter throws "no running loop" in this Flet
        build.
        ⚠ The whole thing **swallows failures** (`try/except`): it only makes the bar appear earlier;
        on failure it degrades to "appears after you scroll", and it must never crash the dialog.
        """
        targets = [c for c in hbars]
        if not targets:
            return

        async def _go() -> None:
            # 等一帧：`page.update()` 之后控件才真的挂上去，此时滚动才有"可滚区间"。
            # [EN] Wait a frame: controls are only really mounted after `page.update()`, and only then
            # [EN] is there a scrollable extent.
            await asyncio.sleep(0.45)
            for s in targets:
                try:
                    await s.scroll_to(offset=1, duration=0)
                    await asyncio.sleep(0.2)
                    await s.scroll_to(offset=0, duration=0)
                    PRIME_LOG.append('ok')
                except Exception as e:                       # noqa: BLE001
                    PRIME_LOG.append(f'ERR {type(e).__name__}: {e}'[:160])
        try:
            page.run_task(_go)
            PRIME_LOG.append(f'task started ×{len(targets)}')
        except Exception as e:                               # noqa: BLE001
            PRIME_LOG.append(f'run_task ERR {type(e).__name__}: {e}'[:160])

    def refresh_all() -> None:
        build_heads()
        build_col1()
        build_col2()
        build_col3()
        build_col4()
        page.update()

    # ── 删除一个项目的用量记录 ──
    # [EN] -- delete one project's usage records --
    def _ask_delete(name: str, calls: int, cost: float) -> None:
        """先问清楚再删。**把要删的东西列出来** —— 只写"确定吗？"的确认框等于没确认。

        ★ 用 `app._confirm_danger`（拾卷删存档用的是同一个）：朱砂色确认按钮、
          确认框**收掉之后**才动手、自带「取消」。
          本模块不能 import `app_flet`（循环导入），但**调用 app 身上的方法**没有这个问题
          —— 这是"复用一个实现"和"不引入 import"两者都要拿到的正解。
        ★ 兜底：`app` 没有那个方法时（判据里的替身 app）自己拼一个同样按钮文案的框，
          免得"点了删除一点反应都没有"。**两条路的按钮文案一致**，所以判据按
          "界面上有没有「确认删除」这个按钮"找就得。
        
                English:
        Ask clearly before deleting. **List out what will be deleted** —— a confirmation box that only
        says "Are you sure?" is as good as no confirmation.
                ★ Use `app._confirm_danger` (the same one used by 拾卷 to delete saves): cinnabar-colored confirm button,
                  act only **after** the confirmation box is dismissed, comes with its own "Cancel".
                  This module can't import `app_flet` (circular import), but **calling a method on the app object** doesn't have this problem
                  —— this is the correct solution that achieves both "reuse one implementation" and "don't introduce an import".
                ★ Fallback: when `app` doesn't have that method (the stand-in app in tests) build a box yourself with the same button text,
                  to avoid "clicking delete does nothing at all". **The button text is identical on both paths**, so the test can just look for
        """
        lines = [
            ft.Text(t('项目：{name}', name=name), size=12, color=_c(colors, 'ink'),
                    selectable=True),
            ft.Text(t('将删除 {n} 次调用记录 · 合计 {c}', n=calls, c=_money(cost)),
                    size=12, color=_c(colors, 'ink')),
            ft.Text(t('只删统计台账里的记录 —— 小说项目本身一个字都不会动。'),
                    size=11, color=_c(colors, 'muted')),
            ft.Text(t('删掉之后无法恢复。'), size=11, color=_c(colors, 'seal')),
        ]
        # ⚠ 局部变量**不许叫 `ask`**：这几支判据用"源码里有没有 `ask(`"
        #   粗查"界面调没调模型"，起这个名字会被当场误判成"调了模型"（假红）。
        #   —— 假红比漏报更坏：看多了就没人看这一项了。
        # [EN] ⚠ The local variable **must not be named `ask`**: those checks use "does the source contain
        # [EN] `ask(`"
        # [EN] to crudely detect "does the UI call the model"; naming it that would trigger a false red for
        # [EN] "called the model".
        # [EN] -- False reds are worse than missed reports: once you see too many, nobody looks at this check
        # [EN] anymore.
        confirm_danger = getattr(app, '_confirm_danger', None)
        if callable(confirm_danger):
            confirm_danger(t('删除这个项目的用量记录'), lines,
                           lambda: _do_delete(name))
            return
        def _yes(e=None) -> None:
            page.pop_dialog()                    # 先收确认框，再动手（与 _confirm_danger 一致）
            # [EN] Collect the confirmation box first, then act (consistent with _confirm_danger)
            _do_delete(name)
        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(t('删除这个项目的用量记录'), size=13,
                          color=_c(colors, 'ink')),
            content=ft.Container(content=ft.Column(lines, spacing=6),
                                 width=430, height=190),
            actions=[ft.TextButton(content=ft.Text(t('确认删除')),
                                   on_click=_yes),
                     ft.TextButton(content=ft.Text(t('取消')),
                                   on_click=lambda e: page.pop_dialog())]))

    def _do_delete(name: str) -> None:
        n = U.delete_project(name, path=path)
        if n < 0:
            # ★ 静默失败 = "以为删掉了、列表却没变"，本项目最忌讳那一种。
            #   所以"没删成"要**说出来**（`delete_project` 也是为此返回 -1 的）。
            # [EN] ★ Silent failure = "thought it was deleted, but the list didn't change", the thing this project
            # [EN] fears most.
            # [EN] So "it didn't get deleted" must be **stated out loud** (`delete_project` returns -1 for this
            # [EN] reason too).
            tip.value = t('删除失败 —— 台账库写不进去（被占用？详见日志）')
        else:
            tip.value = t('已删除 {n} 条用量记录', n=n)
        if st['scope'] == name:
            # 删掉的正是当前选中的项目 ⇒ 退回「软件整体」，
            # 别停在一个**已经不存在的范围**上（那样四栏会全空，看起来像坏了）。
            # [EN] If what was deleted is exactly the currently selected project ⇒ fall back to "whole software",
            # [EN] don't stay on a **range that no longer exists** (that would leave all four columns empty and
            # [EN] look broken).
            _pick_scope(None)
        else:
            refresh_all()

    # ── 导出 ──
    # [EN] -- export --
    def _do_export(e) -> None:
        scope = st['scope']
        name = REPORT.default_name(scope, lang=st['lang'])
        try:
            out = REPORT.build(scope, U.db_path().parent / 'exports' / name,
                               lang=st['lang'], since=st['since'] or None, path=path)
            tip.value = t('已导出：{name}', name=out.name)
            _LOG.info('用量报告导出：%s', out)
        except Exception as exc:                                 # noqa: BLE001
            tip.value = t('导出失败：{e}', e=repr(exc))
            _LOG.warning('导出失败：%r', exc)
        page.update()

    # ── 顶栏 ──
    # [EN] -- top bar --
    lang_dd = ft.DropdownM2(width=104, dense=True, value='zh', label='',
                            options=[ft.dropdownm2.Option(key='zh', text='中文'),
                                     ft.dropdownm2.Option(key='en', text='English')])

    def _on_lang(e) -> None:
        st['lang'] = lang_dd.value or 'zh'
        page.update()

    def _close(e=None) -> None:
        """右上（Win）/ 左上（macOS、Linux）那个「×」。

        ⚠ 用 `pop_dialog()` 而不是 `page.close(...)`：Flet 1.0 的 `Page`
          没有 `open()`（本文件上一版就是栽在这上面），对应地也没有 `close()`。
          叠着确认框时它收的是**最上面那一层**，所以这个「×」只关自己。
        
                English:
        The "×" at top-right (Win) / top-left (macOS, Linux).
                ⚠ Use `pop_dialog()` instead of `page.close(...)`: Flet 1.0's `Page`
                  has no `open()` (the previous version of this file tripped over exactly this), and correspondingly no `close()`.
                  When confirmation boxes are stacked it dismisses the **topmost layer**, so this "×" only closes itself.
        """
        pg = getattr(e, 'page', None) or page
        pg.pop_dialog()

    lang_dd.on_change = _on_lang

    # ★ 标题行与工具行**分成两行**：这样「×」能贴到对话框真正的右上角，
    #   而不是跟在 tip 后面（原来只有一行、还 `wrap=True`，"×"会被挤到中间去）。
    # [EN] ★ The title row and tool row are **split into two rows**: this way the "×" can stick to the
    # [EN] dialog's actual top-right corner,
    # [EN] instead of tagging along after the tip (originally it was one row with `wrap=True`, so the "×"
    # [EN] got squeezed into the middle).
    close_btn = _icon_btn(ft.Icons.CLOSE, _close, colors=colors,
                          tooltip=t('关闭'))
    title_txt = ft.Text(t('LLM 用量'), size=15, weight=ft.FontWeight.BOLD,
                        color=_c(colors, 'ink'), expand=True)
    title_row = ft.Row(
        ([close_btn, title_txt] if _close_side() == 'left'
         else [title_txt, close_btn]),
        spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    # ★ 顶上这一行**只剩导出相关**了（2026-10-11）：「划分」「自」两个筛选已经
    #   搬进第 2 / 第 3 栏的栏头菜单 —— 用户原话「而不是单独放一个地方」。
    # [EN] ★ This top row now contains **only export-related things** (2026-10-11): the "division" and "by"
    # [EN] filters have
    # [EN] moved into the column-header menus of columns 2 / 3 -- user's exact words: "rather than in a
    # [EN] separate spot".
    tools_row = ft.Row([
        ft.Text(t('导出语言'), size=11, color=_c(colors, 'muted')),
        lang_dd,
        _btn(t('导出 xlsx'), _do_export),
    ], spacing=8, wrap=True)
    head = ft.Column([title_row, tools_row], spacing=6)

    # ★ 第 1~3 栏**固定宽**、第 4 栏 `expand=True` 吃掉剩下的全部宽度。
    #   （原来的 `_pane(col1, 170, …)` 那种写法因为 `expand=True` 而**完全没生效**，
    #    四栏等宽 —— 详见 `PANE_W` 那段的说明。）
    # [EN] ★ Columns 1-3 have **fixed widths**, column 4 uses `expand=True` and eats all remaining
    # [EN] width.
    # [EN] (The old `_pane(col1, 170, ...)` form **had no effect at all** because of `expand=True`;
    # [EN] all four were equal -- see the explanation at `PANE_W`.)
    body = ft.Row([
        _pane(col1, PANE_W[1], colors, head1, 1, expand=False),
        _pane(col2, PANE_W[2], colors, head2, 2, expand=False),
        _pane(col3, PANE_W[3], colors, head3, 3, expand=False),
        _pane(col4, 0, colors, head4, 4, expand=True),
    ], spacing=PANE_GAP, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

    # 对话框**默认最大化**：铺满窗口，每边只留 `DLG_MARGIN`。
    # ⚠ 尺寸在**打开这一刻**算一次。窗口之后被缩放，对话框不跟着变 ——
    #   那需要一条 `on_resized` 通路，而它要去碰一个可能已经被关掉的对象；
    #   重开一次就重新算，够用了（这条路也写进判据：关掉再开必须等于新窗口的尺寸）。
    # [EN] The dialog is **maximized by default**: fills the window, leaving only `DLG_MARGIN` on each
    # [EN] side.
    # [EN] ⚠ The size is computed **once, at open time**. If the window is later resized the dialog
    # [EN] does not follow -- that would need an `on_resized` path that touches a possibly-closed
    # [EN] object; reopening recomputes, which is sufficient (this is also covered by a criterion:
    # [EN] closing and reopening must match the new window size).
    # ★★ 必须拿**客户区**（`page.width` / `page.height`），**不是** `page.window.*`。
    #   实测（`developers/probe_window_metrics.py`，本机最大化）：
    #     `page.window.height = 1168` 而 `page.height = 1129`（= 截图的像素高），
    #     差 **39px** —— 那是**标题栏 / 窗口边框**。`page.window.width` 同理差 16px。
    #   用 `page.window.height` 算"最大化"，对话框会比**可视区**还高：
    #   屏幕上看起来只是"底部内容没了"，而判据 `verify_dialog_heights` 的
    #   「高度不超过窗口」当场红（用量统计=1144 > 1129）—— **是那条判据救的场**。
    # [EN] ★★ Must use the **client area** (`page.width` / `page.height`), **not** `page.window.*`.
    # [EN] Measured (`developers/probe_window_metrics.py`, maximized on this machine):
    # [EN] `page.window.height = 1168` while `page.height = 1129` (= the screenshot's pixel height), a
    # [EN] difference of **39px** -- that is the **title bar / window border**. `page.window.width`
    # [EN] differs likewise by 16px.
    # [EN] Using `page.window.height` to compute "maximized" makes the dialog taller than the **usable
    # [EN] area**: on screen it merely looks like "the bottom content is gone", while the criterion
    # [EN] "height does not exceed the window" in `verify_dialog_heights` went red on the spot (usage
    # [EN] stats = 1144 > 1129) -- **that criterion saved the day**.
    size = page.width or page.window.width or 1280
    height = page.height or page.window.height or 800
    dlg_w = max(DLG_MIN_W, int(size) - DLG_MARGIN * 2)
    dlg_h = max(DLG_MIN_H, int(height) - DLG_MARGIN * 2)
    dlg = ft.AlertDialog(
        modal=False,
        content=ft.Container(
            content=ft.Column([head, tip,
                               ft.Divider(height=1, color=_c(colors, 'border')), body],
                              spacing=8, expand=True),
            width=dlg_w,
            height=dlg_h,
        ),
    )
    # ⚠ 是 `show_dialog`：Flet 1.0 的 `Page` **没有 `open()`**（那是旧版写法）。
    #   原来这里写 `page.open(dlg)` ⇒ `AttributeError: 'Page' object has no attribute
    #   'open'` ⇒ 加上前面那几处 `ft.padding.*`，这个对话框**一次都没打开成功过**。
    #   `tools/verify_dialog_heights.py` 现在会"真打开每一个不需要夹具的对话框"，
    #   所以这一类"点了没反应"以后跑一次判据就能发现。
    #: 判据用的抓手 —— 真机脚本靠它读"现在筛的是哪个"（别让判据去猜）。
    #: 与 `app_flet._export_ui` 同一个用意：状态挂出来，判据才写得实。
    # [EN] ⚠ It's `show_dialog`: Flet 1.0's `Page` **has no `open()`** (that's the old-style call).
    # [EN] Originally this read `page.open(dlg)` ⇒ `AttributeError: 'Page' object has no attribute
    # [EN] 'open'` ⇒ combined with the earlier `ft.padding.*` issues, this dialog **never once opened
    # [EN] successfully**.
    # [EN] `tools/verify_dialog_heights.py` now "actually opens every dialog that needs no fixture",
    # [EN] so this class of "clicked and nothing happened" can be caught by running the checks once in the
    # [EN] future.
    # [EN] : Handles for the checks -- the on-device script uses them to read "which filter is currently
    # [EN] selected" (don't make the checks guess).
    # [EN] : Same intent as `app_flet._export_ui`: expose the state so the criteria can be written
    # [EN] concretely.
    dlg._usage_state = st
    page.show_dialog(dlg)
    refresh_all()


def _pane(col: ft.Column, width: int, colors: dict | None,
          head: ft.Control | None = None, tag: int = 0,
          *, expand: bool = False) -> ft.Control:
    """四栏里的一栏：**栏头（表头） + 可滚动的内容**。

    ★ 栏头放在**滚动区之外** —— 这正是"表头"该有的行为：内容滚起来，
      筛选菜单还钉在顶上（用户 2026-10-11 要的就是这个）。
    `tag` 是判据用的抓手（真机脚本靠它认出"这是第几栏"），不参与布局。

    ★★ `expand` 与 `width` **只能给一个**（2026-10-11 修的）：
      Flet 里 `expand=True` 会把控件包进 `Expanded`，它拿到的是"强制撑满"的约束
      —— **`width` 会被彻底忽略**。上一版两个都给了，于是四个"不同宽度"的栏
      实际全是 ~442px 等宽（实测见 `developers/probe_usage_widths.py`）。
      · `expand=False`（第 1~3 栏）⇒ 用 `width`；
      · `expand=True`（第 4 栏）⇒ 吃掉剩下的全部宽度，**不传 `width`**。

        English:
    One of the four columns: **column header (table header) + scrollable content**.
        ★ The column header goes **outside the scroll area** — this is exactly how a "table header" should behave: content scrolls,
          while the filter menu stays pinned to the top (this is what the user wanted on 2026-10-11).
        `tag` is the handle used for identification (the real-device script relies on it to recognize "which column this is"), and does not participate in layout.
        ★★ `expand` and `width` **must not both be given** (fixed 2026-10-11):
          In Flet, `expand=True` wraps the control in an `Expanded`, which receives "forced to fill" constraints
          —— **`width` is completely ignored**. The previous version passed both, so the four "different width" columns
          were in fact all ~442px equal (measurements in `developers/probe_usage_widths.py`).
          · `expand=False` (columns 1-3) ⇒ use `width`;
          · `expand=True` (column 4) ⇒ eats all remaining width, **no `width` passed**.
    """
    kids: list[ft.Control] = []
    if head is not None:
        kids += [head, ft.Divider(height=1, color=_c(colors, 'border'))]
    kids.append(col)
    box = ft.Container(
        content=ft.Column(kids, spacing=6, expand=True),
        padding=_pad_all(6),
        border=_border(1, _c(colors, 'border')),
        border_radius=8,
    )
    if expand:
        box.expand = True
    else:
        box.width = width
    box._usage_pane = tag
    return box
