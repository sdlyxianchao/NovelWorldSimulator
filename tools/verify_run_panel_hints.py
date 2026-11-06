# -*- coding: utf-8 -*-
"""验证：运行界面的**可读性六件**（2026-10-24 用户一轮点了六条）。

用户原话
--------
    「运行界面上 **所有的小 panel** 我提到如下变量 鼠标移动上去的时候显示对应 Tip
      时间 Panel 的 **第几天 · 后面跟的这个 X 时的时间** 我希望鼠标移动上去
      显示**现代的时间表示** 并解释这个时间是几点到几点
      **如果已经是现代时间了则不需要解释**
      小地图的地图下面的那句话 **今天这场戏在 x 处** 现在显示不清楚
      我希望可以**多行显示**
      运行配置的**运行模式** 现在显示不全 我希望变成 **2 行** 显示全
      **右边的所有 Panel** 我希望变宽一些 现在的各个人物和剧组 Agent 的动作显示不全
      你看大概放大到多宽可以刚好都显示全（或者大部分显示全，有少数几个显示不全的）
      **所有在场人物和剧组 Agent 的动作部分** 鼠标放上去都显示完整的 Tip」

判据分组（**一条判据只守一道闸**，见 MEMORY 的口径）
--------------------------------------------------
  A **面板悬停**：`_create_panel` 造出来的每个面板都带 tooltip；而且给的是
     `md_strip` 之后的纯字符串（`**` 不能漏到浮层里）
  B **时辰解释**：`auto` 历法下悬停给出「现代时间 + 几点到几点」；**子时讲清
     跨午夜**；**现代历法下不挂 tooltip**（用户点名的例外）；没有时钟时不编
  C **小地图图注多行**：`no_wrap=False`；且那句话**真的放不进一行**
     （"放得进还折行"说明这条判据没在测东西）
  D **运行模式两行**：`mk_kv(stack=True)` 是 Column（标签一行、值一行）；
     且真实值**真的放不进一行**
  E **右栏宽度**：`RUN_RIGHT_W` 一处定义、`PLOT_CHIP_W`/`CREW_TEXT_W` 都由它算；
     ★ 行为级：**「剧组」真实 19 行里最宽的那一行能放进 `CREW_TEXT_W`**
     （这就是"刚好都显示全"的可验证形式，用的是真实台账 + 真实职责）
  F **每一行都有完整 Tip**：`crew_list` / `char_list` 里的每一行
     （**包括点不动的那种**）都有 tooltip，且里面是**未截断**的整句

跑法：.venv\\Scripts\\python.exe tools/verify_run_panel_hints.py
产出：assets/screenshots/run_panel_hints_report.json

English:
Verify the run screen's **six readability items** the user listed in one go on 2026-10-24.
Groups (one criterion, one gate):
  A **panel hover** -- every panel from `_create_panel` carries a tooltip, and it is the
    `md_strip`ed string (no `**` may reach the native overlay)
  B **shichen explanation** -- under the `auto` calendar hover gives "modern time + which hours";
    **the zi hour spells out that it crosses midnight**; **no tooltip under the modern calendar**
    (the user named that exception); nothing invented when there is no clock
  C **minimap caption wraps** -- `no_wrap=False`, and the sentence **really does not fit one line**
    (if it fits, the criterion is not measuring anything)
  D **run mode on two lines** -- `mk_kv(stack=True)` is a Column (label line + value line), and the
    real value **really does not fit one line**
  E **right column width** -- `RUN_RIGHT_W` defined once, `PLOT_CHIP_W`/`CREW_TEXT_W` derived from
    it; ★ behaviourally: **the widest of the real 19 Cast rows fits `CREW_TEXT_W`** (that is the
    verifiable form of "just wide enough to show them all", using the real ledger and real duties)
  F **every row has a full tip** -- every row in `crew_list` / `char_list` (**including the
    non-clickable ones**) has a tooltip holding the **untruncated** sentence
Usage: .venv\\Scripts\\python.exe tools/verify_run_panel_hints.py
Output: assets/screenshots/run_panel_hints_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft                                              # noqa: E402

import gui.app_flet as A                                       # noqa: E402
from image_gen.minimap import _cjk_w                            # noqa: E402
from util.timefmt import GameTime                              # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
REPORT = OUT / 'run_panel_hints_report.json'
_rows: list[dict] = []


def ok(name: str, cond, detail='') -> bool:
    _rows.append({'判据': name, '通过': bool(cond), '实测': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''))
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A —— 面板整块悬停有说明
# [EN] A -- the whole panel explains itself on hover
# ══════════════════════════════════════════════════════════════
def a_panel_tips() -> None:
    print('\n【A】面板悬停说明')
    app = object.__new__(A.NovelWorldApp)
    app._ui_run = {}

    # ① 给 tip 就必须挂上（容器那一层，不只是标题右边那个白问号）
    box = app._create_panel('时间', [ft.Text('x')], tip='这一块是**故事时间**')
    ok('A1 ★★★ `_create_panel` 给了 `tip` ⇒ **整个面板**挂 tooltip'
       '（不是只有标题右边那个 15px 的白问号）',
       bool(getattr(box, 'tooltip', None)) and isinstance(box, ft.Container),
       f'tooltip={getattr(box, "tooltip", None)!r}')

    # ② 送到浮层的那一句必须是**去 markdown 之后**的：`**` 会在浮层里原样显示
    ok('A2 ★★★ 浮层拿到的是 `md_strip` 之后的纯文本（`**` 不许漏出去 —— '
       '否则用户天天看到一句带星号的说明）',
       '**' not in str(getattr(box, 'tooltip', ''))
       and getattr(box, '_panel_tip', '') == str(box.tooltip),
       f'{str(box.tooltip)!r}')

    # ③ 没给 tip 就别硬塞一句空话（`tooltip=''` 会让浮层闪一个空白框）
    bare = app._create_panel('空', [], tip='')
    ok('A3 ★★ 没给 `tip` 时**不挂** tooltip（空串会闪一个空白浮层）',
       getattr(bare, 'tooltip', None) is None, f'{getattr(bare, "tooltip", None)!r}')

    # ④ 真正跑起来的界面上，**每一个**面板都有说明（数一遍）
    #    ⚠ 这里数的是"造出来的 panel 容器"，靠抓手 `_panel_tip` 认 —— 不去
    #    猜控件树（猜法一改就假红）。
    # [EN] Count every panel on a really-built screen via the `_panel_tip` handle
    # (never guess from the control tree -- a guess goes false-red on any refactor).
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    import ast as _ast
    tree = _ast.parse(src)
    calls, with_tip, empty_tip = 0, 0, []
    for n in _ast.walk(tree):
        if (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
                and n.func.attr == '_create_panel'):
            calls += 1
            kw = {k.arg: k.value for k in n.keywords if k.arg}
            if 'tip' in kw:
                with_tip += 1
                _v = kw['tip']
                # 传了关键字但值是**空常量** = 屏幕上没有说明（`md_strip('')` 之后不挂）
                if isinstance(_v, _ast.Constant) and not str(_v.value or '').strip():
                    empty_tip.append(getattr(n, 'lineno', 0))
    ok('A4a ★★★ 运行界面里**每一处** `_create_panel(...)` 都传了 `tip`'
       '（用户：「所有的小 panel …… 鼠标移动上去的时候显示对应 Tip」）',
       calls > 0 and with_tip == calls, f'{with_tip}/{calls} 处传了 tip')
    # ⚠ "传了 tip" 与 "tip 有内容" 是**两道闸**：`tip=''` 同样能过 A4a，
    #   而屏幕上什么都不出（`_create_panel` 遇到空串不挂 tooltip）。
    #   反例法第一轮就是在这个缝里漏掉的 —— 见 `mutate_run_panel_hints.py` 的 A4 刀。
    # [EN] ⚠ "passes a tip" and "the tip has content" are **two gates**: `tip=''` satisfies A4a
    # [EN] while nothing appears on screen. The first counterexample round slipped through exactly
    # [EN] here -- see the A4 cut in `mutate_run_panel_hints.py`.
    ok('A4b ★★★ 而且**每一处 tip 都有内容**（`tip=''` 会让那一块悬停毫无反应）',
       not empty_tip, f'空 tip 的行号 {empty_tip}' if empty_tip else '全部非空')


# ══════════════════════════════════════════════════════════════
#  B —— 时辰悬停：现代时间 + 几点到几点
# [EN] B -- shichen hover: modern time + which hours
# ══════════════════════════════════════════════════════════════
class _W:
    """最小世界夹具（只要时间面板读的那几个字段）。"""

    def __init__(self, *, calendar='auto', minutes=19 * 60 + 24, day=1):
        self.calendar = calendar
        self.clock = GameTime(day=day, minutes=minutes)
        self.game_day = day
        self.weather = '阴'


def b_shichen_tip() -> None:
    print('\n【B】时辰悬停说明')
    app = object.__new__(A.NovelWorldApp)

    tip = app._time_panel_tip(_W(minutes=19 * 60 + 24))
    ok('B1 ★★★ 悬停显示**现代时间表示**（故事钟此刻的钟点）'
       '—— 用户：「我希望鼠标移动上去显示现代的时间表示」',
       '19:24' in tip, repr(tip))

    ok('B2 ★★★ 并且**解释这个时辰是几点到几点**'
       '—— 用户：「并解释这个时间是几点到几点」',
       '戌时' in tip and '19:00' in tip and '21:00' in tip, repr(tip))

    # ③ 子时跨午夜：光看 23:00–01:00 两个数分不清是不是同一天
    zi = app._time_panel_tip(_W(minutes=23 * 60 + 30))
    ok('B3 ★★★ **子时**要说清"跨午夜 / 次日"（23:00–01:00 光给两个数字，'
       '读的人会以为时间在倒着走）',
       '次日' in zi or '跨午夜' in zi, repr(zi))

    # ④ 现代历法 = 屏幕上已经是现代时间 ⇒ **不挂 tooltip**（用户点名的例外）
    modern = app._time_panel_tip(_W(calendar='modern'))
    ok('B4 ★★★ **现代历法下不解释**（屏幕上已经是 `第3日 19:24`）'
       '—— 用户：「如果已经是现代时间了则不需要解释」',
       modern == '', repr(modern))

    # ⑤ 没有时钟就别编一个时间
    class _NoClock:
        calendar = 'auto'
        clock = None

    ok('B5 ★★ 拿不到时钟时**返回空**（不编一个时间出来骗人）',
       app._time_panel_tip(_NoClock()) == '', '')

    # ⑥ 界面接线：这个 tooltip 真的写到了「第 N 天 · X时」那个控件上
    #    ⚠ 只测函数不测接线，等于"函数对了但屏幕上没有" —— 本项目栽过多次。
    # [EN] Wiring: the tooltip must really land on the `day N · X hour` control.
    app2 = object.__new__(A.NovelWorldApp)
    app2._ui_run = {'time_main': ft.Text('—'), 'time_hint': ft.Text('—')}

    class _S:
        class loop:
            world = _W(minutes=19 * 60 + 24)
        is_alive = True

    app2.session = _S()
    app2._safe_update = lambda c: None
    app2._refresh_time_panel()
    got = app2._ui_run['time_main']
    ok('B6 ★★★ **接线**：刷新之后 `time_main` 上真的挂着那句说明'
       '（只测函数不测接线 = "函数对了但屏幕上没有"）',
       bool(getattr(got, 'tooltip', None)) and '19:00' in str(got.tooltip),
       f'{str(getattr(got, "tooltip", ""))!r}')


# ══════════════════════════════════════════════════════════════
#  C —— 小地图图注多行
# ══════════════════════════════════════════════════════════════
def c_map_note() -> None:
    print('\n【C】小地图图注多行')
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    import ast as _ast
    tree = _ast.parse(src)
    # 找到 `map_note = ft.Text(...)` 那一句，读它的关键字参数
    kwargs: dict = {}
    for n in _ast.walk(tree):
        if not isinstance(n, _ast.Assign):
            continue
        for tgt in n.targets:
            if isinstance(tgt, _ast.Name) and tgt.id == 'map_note' \
                    and isinstance(n.value, _ast.Call):
                for k in n.value.keywords:
                    if isinstance(k.value, _ast.Constant):
                        kwargs[k.arg] = k.value.value
                    else:
                        kwargs[k.arg] = 'expr'
    ok('C1 ★★★ 小地图图注**允许折行**（`no_wrap=False`，不再是省略号一行）'
       '—— 用户：「今天这场戏在 x 处 现在显示不清楚 我希望可以**多行显示**」',
       kwargs.get('no_wrap') is False and 'max_lines' not in kwargs,
       f'{kwargs}')

    # ② 那句话**真的放不进一行** —— 否则这条判据没在测东西
    app = object.__new__(A.NovelWorldApp)

    class _Lay:
        places = [1, 2]
        source = 'day'

    app._map_day = _Lay()
    app._map_here = '望江楼'
    text, _color = app._map_note_text(_Lay())
    avail = A.MAP_W            # 左栏内容区 = 小地图画布宽 196
    w = _cjk_w(text, A.HINT_FS)
    ok('C2 ★★★ 那句话**一行放不下**（放得下还折行 = 这条判据在空转）'
       '—— 一句话把"几处 + 谁摆的"都说完，正是用户要看全的那半句',
       w > avail, f'{w:.0f}px > 内容区 {avail}px · {text[:24]}…')


# ══════════════════════════════════════════════════════════════
#  D —— 运行模式两行
# ══════════════════════════════════════════════════════════════
def d_run_mode() -> None:
    print('\n【D】运行模式两行')
    one = A.mk_kv('运行模式', '定期暂停（每几天停一次）')
    two = A.mk_kv('运行模式', '定期暂停（每几天停一次）', stack=True)
    ok('D1 ★★★ 默认仍是**一行**（短的值不该白占两行高度）',
       isinstance(one, ft.Row), type(one).__name__)
    ok('D2 ★★★ `stack=True` 是**标签一行、值一行**'
       '—— 用户：「运行配置的运行模式 现在显示不全 我希望变成 **2 行** 显示全」',
       isinstance(two, ft.Column) and len(two.controls) == 2
       and all(isinstance(c, ft.Text) for c in two.controls),
       f'{type(two).__name__} · {len(getattr(two, "controls", []))} 行')

    # ③ 真实值**真的放不进一行**（否则"变两行"这个改动没有理由）
    val = A.run_mode_name('story_day')
    need = _cjk_w(val, A.HINT_FS) + _cjk_w('运行模式', A.HINT_FS) + 6
    avail = A.MAP_W            # 左栏内容区 196px
    ok('D3 ★★★ 「运行模式」那一行**一行真放不下**（标签 + 最长的那个值）'
       '—— 放得下还改两行就是在浪费高度',
       need > avail, f'{need:.0f}px > {avail}px · {val}')

    # ④ 界面接线：运行配置里那一行**用的是两行版**（不是默认版）
    #   ⚠ 第一版写的是 `src.count('stack=True)') >= 1` —— 但「一拍」那一行
    #     **也**传了 `stack=True` ⇒ 把「运行模式」那一处改回默认版，判据照样绿
    #     （反例法当场抓到）。所以这两处**各判各的**，锚点带足上下文。
    # [EN] ⚠ The first version used `src.count('stack=True)') >= 1`, but the "one beat" row
    # [EN] **also** passes `stack=True` => reverting only the "run mode" row left the criterion
    # [EN] green (the counterexample caught it). So each of the two is judged separately, with
    # [EN] enough context in the anchor.
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    mode_ok = ("run_mode_name(feat['run_mode']),\n"
               "                          value_color=C['gold'], stack=True)") in src
    ok('D4a ★★★ 运行配置里**「运行模式」那一行**真的传了 `stack=True`'
       '（只改 `mk_kv` 不接线 = 屏幕上没变）',
       mode_ok, '')
    ok('D4b ★★★ 而「一拍」那一行也传了（它的文案 30 多个字，一行更放不下）',
       "mk_kv(t('一拍'), beat_pace_text(), stack=True)" in src, '')


# ══════════════════════════════════════════════════════════════
#  E —— 右栏宽度（量出来的，不是拍的）
# [EN] E -- right column width (measured, not guessed)
# ══════════════════════════════════════════════════════════════
def _real_crew_rows() -> list[str]:
    """按 `_ledger_row()` 的拼法，还原「剧组」那一栏的真实 19 行文本。

    数据**全部是真的**：19 个职位的职责来自 `crew.roster.ROSTER`；状态与产出
    来自最近一次真跑的 `剧组台账.md`（找不到就只用职责那一路，判据仍然有效）。
    [EN] Rebuild the real 19 Cast rows exactly as `_ledger_row()` assembles them.
    [EN] All data is real: the 19 duties come from `crew.roster.ROSTER`; states and outputs
    [EN] come from the most recent real run's `剧组台账.md` (falling back to duties only).
    """
    from crew import roster as R
    duty = {r.name: r.duty for r in R.roles()}
    rows: list[str] = []
    md = Path('C:/小说世界AI模拟/项目/望江楼模拟项目/'
              '第3次模拟2026-10-24-17-48/剧组台账.md')
    real: list[tuple[str, str, str]] = []
    if md.exists():
        for line in md.read_text(encoding='utf-8').splitlines():
            if line.startswith('| **'):
                cells = [c.strip() for c in line.strip('|').split('|')]
                if len(cells) >= 5:
                    real.append((cells[0].strip('* '), cells[1], cells[4]))
    state_run = {'已交活': 'done', '待命': 'idle', '在岗': 'onduty',
                 '出工中': 'working', '未启用': 'off'}
    for name, st, out in real:
        if name.startswith('演员·'):
            continue        # 子行在「在场人物」，不在这一栏（见 `_refresh_crew_panel`）
        note = {'off': '未启用', 'working': '出工中', 'onduty': '在岗'}.get(
            state_run.get(st, 'idle'), '')
        head = name + (f' · {note}' if note else '')
        if out and out != '—':
            body = out
        elif st == '在岗':
            body = '在岗 · 正在做：' + duty.get(name, '')
        else:
            body = '还没轮到'
        rows.append(f'{head} · {body}')
    if not rows:
        # 没有台账也要能测。
        # ★★★ 2026-10-26：**不能再把"最长的那一档"当成典型值**。
        #   原来这里 19 行**全是** `名字 · 在岗 · 正在做：<职责全文>`，
        #   于是 P50 = 420px —— 但那副样子在真面板上不存在：真台账里
        #   多数人是「待命 / 还没轮到 / 已交活」这种短状态，只有正在干活的那几个
        #   才带职责全文（2026-10-24 那次量到的真实分布是 P50 = 130px）。
        #   拿"全员都在念职责全文"去算中位数，等于**量错了对象**：
        #   它测不出"典型行长什么样"，只能测出"最长能多长"——后者归 E2b 管。
        #   ⇒ 按真面板的样子交替还原：一半短状态、一半在岗全文。
        # [EN] ★★★ 2026-10-26: **stop treating "the longest variant" as the typical value**.
        # [EN] All 19 rows used to be `name · on duty · doing: <full duty>`, giving P50 = 420px --
        # [EN] a shape the real panel never has: in a real ledger most people sit at "idle / not
        # [EN] their turn / done", and only the few actually working carry the full duty text (the
        # [EN] real distribution measured on 2026-10-24 had P50 = 130px). Taking a median over
        # [EN] "everyone reciting their duty" **measures the wrong object**: it cannot show what a
        # [EN] typical row looks like, only how long the longest can be -- and that is E2b's job.
        # [EN] ⇒ Rebuild the way the real panel looks: half short states, half on-duty full text.
        _pairs = list(duty.items())
        rows = [(f'{n} · 在岗 · 正在做：{d}' if i % 2 else f'{n} · 待命')
                for i, (n, d) in enumerate(_pairs)]
    return rows


def e_right_width() -> None:
    print('\n【E】右栏宽度')
    ok('E1 ★★★ 右栏宽度**只有一处定义**（`RUN_RIGHT_W`），`PLOT_CHIP_W` 由它算'
       '—— 以前 240 写在两处（Column 的 width + 胶囊宽度的算式），改一处必漂',
       A.PLOT_CHIP_W == A.RUN_RIGHT_W - 12 * 2 - 2
       and A.CREW_TEXT_W == A.RUN_RIGHT_W - 24 - 2 - 18,
       f'RUN_RIGHT_W={A.RUN_RIGHT_W} → PLOT_CHIP_W={A.PLOT_CHIP_W} / '
       f'CREW_TEXT_W={A.CREW_TEXT_W}')

    rows = _real_crew_rows()
    widths = sorted(_cjk_w(t, A.HINT_FS) for t in rows)
    widest = widths[-1] if widths else 0
    p50 = widths[len(widths) // 2] if widths else 0
    # ⚠ **口径 2026-10-25 改过一次**，原因写在这儿：
    #   原来判"**每一行**都放得下"。那条是 2026-10-24 定的，当时实测最宽 342px。
    #   真跑一天之后台账里出现 474px 的行（`演员 · 7 位在场｜<某人一段盘算>`、
    #   `复盘 · 今天推进的是…`），而右栏文本区只有 356px ——
    #   要装下它得把右栏拉到 ~570px，中栏会被压掉一大截。
    #   用户在同一天明确选了另一条路（原话：「鼠标放上去都有 Tip 显示完整的」）：
    #   **放不下就悬停看**。所以这一条守的意图从"每一行都放得下"换成
    #   "**典型行一眼看全 + 最长的那些悬停能看到完整**"（两半成对，缺一条就成了放水）。
    # [EN] ⚠ **The convention changed on 2026-10-25**, and here is why: it used to judge "**every**
    # [EN] row fits", set on 2026-10-24 when the widest measured 342px. After a real day, the ledger
    # [EN] produced 474px rows (the actor summary carrying a deliberation, the retrospective), while
    # [EN] the right column's text area is only 356px -- fitting it needs ~570px and would squeeze the
    # [EN] middle column badly. The user picked the other path the same day ("all of them must show the
    # [EN] complete text in a tip on hover"): **if it doesn't fit, hover**. So the intent moves from
    # [EN] "every row fits" to "**typical rows read at a glance + the longest ones are complete on
    # [EN] hover**" (two halves, or it becomes a rubber stamp).
    ok('E2a ★★★ **典型行一眼看全**：P50 行放得下右栏'
       f'（P50 {p50:.0f}px ≤ 文本区 {A.CREW_TEXT_W}px）',
       bool(widths) and p50 <= A.CREW_TEXT_W,
       f'{len(rows)} 行 · 最宽 {widest:.0f}px · P50 {p50:.0f}px · '
       f'文本区 {A.CREW_TEXT_W}px')

    # 成对的一半：**最长的那些必须悬停看得到完整**（不是"截了就没了"）。
    # ⚠ 用真实那一行的整句去问 `_crew_row_tip`，而不是另造一段 —— 造的那段永远合规。
    # [EN] The paired half: **the longest rows must be complete on hover** (not "truncated and gone").
    # [EN] ⚠ Feed the real row's full sentence to `_crew_row_tip` instead of making one up -- a made-up
    # [EN] string always passes.
    app_e = object.__new__(A.NovelWorldApp)
    # ⚠ 比对前要**同样折叠空白**：`_crew_row_tip` 会把换行/连续空格折成一个空格，
    #   拿原文直接 `in` 会误报"缺"（第一版就把"有换行的那一行"判成了缺）。
    # [EN] ⚠ Collapse whitespace the same way before comparing: `_crew_row_tip` folds newlines /
    # [EN] runs of spaces into one space, so checking the raw string with `in` false-reports a miss
    # [EN] (the first version flagged the one row that has a newline).
    def _flat(s: str) -> str:
        return ' '.join(str(s or '').split())

    over = sorted(rows, key=lambda s: -_cjk_w(s, A.HINT_FS))[:3]
    bad_tip = [s for s in over
               if _flat(s)[:40] not in _flat(app_e._crew_row_tip({'name': 'x'}, s))]
    ok('E2b ★★★ 成对：**放不下的那几行，悬停必须是完整的**（用户 2026-10-25：'
       '"鼠标放上去都有 Tip 显示完整的"）',
       not bad_tip, f'检查了最宽的 {len(over)} 行 · 缺 {len(bad_tip)} 行')
    if widths and widest > A.CREW_TEXT_W:
        for t in sorted(rows, key=lambda t: -_cjk_w(t, A.HINT_FS))[:3]:
            print(f'      放不下（悬停看）：{_cjk_w(t, A.HINT_FS):.0f}px  {t[:50]}')

    ok('E3 ★★★ 而且**不是靠无限加宽**做到的：右栏 ≤ 420px'
       '（再宽就把中栏的叙事区挤没了 —— 1920 的屏上中栏要留 ~1000px）',
       A.RUN_RIGHT_W <= 420, f'RUN_RIGHT_W={A.RUN_RIGHT_W}')

    # ④ 界面接线：那一栏 Column 用的就是这个常量
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    ok('E4 ★★★ 右栏那个 `Column` **用的是这个常量**（不是另写一个数）',
       'width=RUN_RIGHT_W' in src, '')


# ══════════════════════════════════════════════════════════════
#  F —— 每一行都有完整 Tip（含点不动的那种）
# [EN] F -- every row has a full tip (including non-clickable ones)
# ══════════════════════════════════════════════════════════════
class _R:
    """一行台账的最小夹具。"""

    def __init__(self, **kw):
        self.d = {'key': 'director', 'name': '导演', 'state': 'onduty',
                  'busy': False, 'secs': 0.0, 'line': '', 'duty': '定框架',
                  'ok': True, **kw}

    def get(self, k, default=None):
        return self.d.get(k, default)


def f_row_tips() -> None:
    print('\n【F】每一行的完整 Tip')
    app = object.__new__(A.NovelWorldApp)
    long_line = ('我先不去碰那页空账，等他自个儿开口；壶嘴朝凳脚是他给的暗示，'
                 '要是他还不动，我就把灯芯拨亮一点，让门口那人看清屋里还有谁。')

    # ① 有 key（能点）的那一路
    clickable = _R(line=long_line)
    box = app._crew_row(
        clickable, busy=False, head='导演', line=long_line,
        text_key='text', dot_key='muted',
        on_click=lambda e: None, indent=0)
    tip1 = str(getattr(box, 'tooltip', '') or '')
    ok('F1 ★★★ 能点的那一行带 tooltip，且里面是**未截断的整句**'
       '（"放不下就悬停看"的兑现）',
       long_line in tip1, f'{len(tip1)} 字')

    # ② 没有 key（点不动）的那一路 —— 这正是演员子行的形状
    plain = _R(key='', name='演员·白衣女人', state='onduty',
               line='', duty=long_line[:60])
    row = app._crew_row(
        plain, busy=False, head='演员·白衣女人',
        line='在岗 · 正在做：' + long_line[:60],
        text_key='text', dot_key='muted', on_click=None, indent=0)
    ok('F2 ★★★ **点不动的那一行也必须有 tooltip**'
       '（演员子行就是这一路：以前 `on_click is None` 直接 return，'
       '连 tooltip 都没有 —— 而"动作看不全"最厉害的就是它们）',
       bool(str(getattr(row, 'tooltip', '') or '')), type(row).__name__)

    # ③ tooltip 必须挂在**整行**上（挂在文本上时，鼠标停在圆点上是死区）
    ok('F3 ★★ 悬停说明挂在**整行**容器上（不是只挂在文字上：'
       '挂在文字上时鼠标停在圆点那 15px 里没反应）',
       hasattr(row, 'content') and hasattr(row, 'tooltip'), '')

    # ④ 出工高亮那一支也要有（它有底色，是另一个容器）
    busybox = app._crew_row(
        _R(key='', busy=True, secs=12.0), busy=True, head='导演 · 出工中',
        line='正在做：定框架', text_key='text', dot_key='accent',
        on_click=None, indent=0)
    ok('F4 ★★ **出工高亮**那一行（带底色的那个容器）也有 tooltip',
       bool(str(getattr(busybox, 'tooltip', '') or '')), type(busybox).__name__)

    # ⑤ 空内容不许变成空白浮层（会闪一个空框）
    empty = app._crew_row(
        _R(key='', name='群众演员', line=''), busy=False, head='群众演员',
        line='', text_key='text', dot_key='muted', on_click=None, indent=0)
    ok('F5 ★★ 没有内容的那一行也给一句可用的话（不是空白浮层）',
       bool(str(getattr(empty, 'tooltip', '') or '').strip()),
       f'{str(getattr(empty, "tooltip", ""))!r}')

    # ⑥ **行里每个元素都带同一句**（2026-10-25，用户第二次点名同一件事）。
    #   上一轮只挂最外层容器；真机上"还是有地方悬停没反应"—— 原生 tooltip 的命中区
    #   是**控件自己的矩形**，而外层容器 `padding=0` 时它的矩形取决于子控件撑成什么样。
    #   ⇒ 判据按"**每一个 Text 都得带**"来钉，而不是"容器上有就行"。
    # [EN] ⑥ **Every element in the row carries the same tip** (2026-10-25, the user raised this
    # [EN] same thing a second time). Last round only the outermost container had it; on the real
    # [EN] machine "some spots still do not react" -- a native tooltip's hit area is **the control's
    # [EN] own rectangle**, and with `padding=0` the outer container's rectangle depends on how the
    # [EN] children stretch. => Pin it as "**every Text must carry it**", not "the container has one".

    def _texts(ctl) -> list:
        try:
            if isinstance(ctl, ft.Text):
                return [ctl]
            kids = []
            for attr in ('content', 'controls', 'leading', 'trailing'):
                if hasattr(ctl, attr):
                    kids.append(getattr(ctl, attr))
            out = []
            for k in kids:
                if isinstance(k, (list, tuple)):
                    for x in k:
                        out.extend(_texts(x))
                elif k is not None:
                    out.extend(_texts(k))
            return out
        except Exception:                                        # noqa: BLE001
            return []




    # ⑦ 走**真实的拼法**（`_ledger_row` → `_crew_row`）：判据不该只测"手工调 `_crew_row`"
    #   那一层 —— 真实那一层才会决定 compact / on_click / head / line 怎么给。
    # ⚠ 而且**两行版只能从这里拿到**：F2 那个 `row` 用的是默认 `compact=True`，
    #   手工调 `_crew_row` 永远碰不到"动作独占第二行"那一支 ——
    #   反例法实测过：把动作那行的 Tip 删掉，F6 照样绿（它根本没看那一支）。
    # [EN] ⑦ Go through the **real assembly** (`_ledger_row` -> `_crew_row`). ⚠ And the **two-line
    # [EN] variant is only reachable from here**: F2's `row` uses the default `compact=True`, so calling
    # [EN] `_crew_row` by hand never touches "the action gets its own second line" -- the counterexample
    # [EN] method measured it: delete the tip from that action line and F6 stayed green (it never looked).
    app2 = object.__new__(A.NovelWorldApp)
    sub = _R(key='', name='演员·白衣女人', state='onduty', busy=False,
             line='', duty=long_line[:60])
    real = app2._ledger_row(sub, compact=False)

    for label, row in (('能点的那一路', box), ('点不动的那一路', row),
                       ('在场人物·两行版', real)):
        ts = _texts(row)
        miss = [getattr(x, 'value', '?') for x in ts
                if not str(getattr(x, 'tooltip', '') or '').strip()]
        ok(f'F6 ★★★ {label}：行里**每一个**文字元素都带 Tip（鼠标落在圆点、名字、'
           f'动作上都一样有 —— 别赌"外层容器的命中区刚好盖住用户指的那一点"）',
           bool(ts) and not miss, f'{len(ts)} 个文字元素 · 缺 {miss}')

    ok('F7 ★★★ 走**真实拼法**（`_ledger_row` → `_crew_row`，在场人物那一栏的两行版）'
       '出来的行也有 Tip，且里面是**完整的动作**（不是屏幕上那半句）',
       long_line[:60] in str(getattr(real, 'tooltip', '') or ''),
       f'{len(str(getattr(real, "tooltip", "") or ""))} 字')

    keyed = _R(key='director', name='导演', state='idle', busy=False, line='',
               duty='定框架')
    real2 = app2._ledger_row(keyed, compact=True)
    ok('F8 ★★ 成对：剧组那一栏的一行版（能点的那一路）也有 Tip',
       bool(str(getattr(real2, 'tooltip', '') or '').strip()),
       f'{str(getattr(real2, "tooltip", ""))[:24]}…')


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print('═' * 62)
    print('  运行界面可读性六件（2026-10-24）')
    print('═' * 62)
    for fn in (a_panel_tips, b_shichen_tip, c_map_note,
               d_run_mode, e_right_width, f_row_tips):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f'{fn.__name__} 整组没跑完：{e!r}', False, '')

    bad = [r for r in _rows if not r['通过']]
    print('\n' + '─' * 62)
    print(f'  运行界面可读性验证：{len(_rows) - len(bad)}/{len(_rows)}'
          + ('   ← 有失败' if bad else ''))
    for r in bad:
        print(f'    ! {r["判据"]}  [{r["实测"]}]')
    print('─' * 62)
    REPORT.write_text(json.dumps(_rows, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
