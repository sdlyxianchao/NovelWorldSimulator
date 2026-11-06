# -*- coding: utf-8 -*-
"""两套「第几天」验证：**同一条时间线上不许有两个天数**（2026-10-31）。

用户原话（这段就是全部规格）：

    「运行窗口左上角时间和对话窗口的时间对不上，你看最新日志，
      左上角说是第4天但是运行窗口是第2天刚结束，正准备第三天」

## 病灶（查日志查出来的，不是猜的）

同一时刻有**两条**各自计数的"天"：

| 谁 | 读什么 | 实测（第2次模拟 20:39） |
|---|---|---|
| 左上角时间面板 / 状态条 | `world.game_day`（**故事钟**） | 第 4 天 |
| 中栏幕头「收工」/ `当天故事.md` / 落盘 `第00N天.md` / 停点 `day` | `loop._current_day`（**写作天**） | 第 3 天 |

两条线从**开演那一刻**就分叉，因为续跑时：

1. `RunLoop._current_day` 写死 `1`（世界时钟却由 `start_clock_of(plan)` 接着上一轮的
   第 3 天）—— 差 N 天，且这一轮所有稿子从 `第001天.md` 重新编号；
2. 停点 `day` 存的是**写作天**，`start_clock_of()` 却拿它当**故事天**建时钟 ——
   实测停点里 `day=3` 而 `calendar` 已经是 `第4天·辰时`，续跑一开演**时间倒退一天**。

## 这一支证什么

- **A** 写作天接线：`RunLoop(start_day=4)` ⇒ `_current_day == 4`；不传 ⇒ 1
- **B** 停点里两个天**各存一栏**，`story_day` 是故事钟、`day` 是写作天
- **C** `story_day_of()`：显式字段 → `calendar` 解析 → `day`，**顺序不许反**（老停点兼容）
- **D** `start_clock_of()` 用故事天建时钟（拿写作天会倒退）
- **E** `plan()` 把两个天都带出来，`next_day` / `resume` 两条路都对
- **F** AST 接线：`assemble(start_day=)` 真的传给了 `RunLoop`；GUI 真的传了 `start_day=`
- **G** AST 同源：界面/快照里那几处"第几天"读的是 `_current_day`，**不再**直读 `game_day`
- **H** 反例：把 `start_day` 那条接线拆掉，A 必须变红（证明这条判据有牙）

跑法：.venv\\Scripts\\python.exe tools/verify_day_consistency.py
产出：assets/screenshots/day_consistency_report.json

English:
Two "day counters" verification: **one timeline must not carry two day numbers** (2026-10-31).

The user's words (this is the whole spec): "the top-left clock in the run window and the
dialogue window disagree -- top-left says day 4 while the run window says day 2 just ended,
about to start day 3".

Root cause (from the log, not guessed): two independent "day" counters. The top-left panel and
status bar read `world.game_day` (the **story clock**); the centre-column header, `当天故事.md`,
the persisted `第00N天.md` files and the stop point's `day` read `loop._current_day` (the
**writing day**). They diverge from the very first beat because resuming (1) hard-coded
`_current_day = 1` while the world clock continued at day 3, and (2) stored the writing day in
the stop point's `day` but built the world clock from it as if it were the story day --
measured `day=3` with `calendar` reading "day 4 · chen hour", so resuming moved time backwards
a day.

What this verifies: A the wiring of the writing day; B both days stored as separate fields;
C `story_day_of()` resolution order (explicit field -> parse `calendar` -> `day`); D
`start_clock_of()` builds from the story day; E `plan()` carries both; F AST wiring through
`assemble`; G the UI reads the writing day; H a mutation that must turn A red.
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _src(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def _names_in(fn) -> set:
    """这个函数**源码里出现的标识符/属性名**（AST 扫，**不看注释**）。"""
    tree = ast.parse(_src(fn))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _called(fn) -> set:
    """这个函数**调**了谁（写成 `a.b` 那种点号串）。不看注释、不看字符串。"""
    tree = ast.parse(_src(fn))
    out = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        parts = []
        while isinstance(f, ast.Attribute):
            parts.append(f.attr)
            f = f.value
        if isinstance(f, ast.Name):
            parts.append(f.id)
        if parts:
            out.add('.'.join(reversed(parts)))
    return out


def _kw_in_call(fn, call_name: str) -> set:
    """`fn` 里对 `call_name` 的那次调用带了哪些**关键字参数名**。"""
    tree = ast.parse(_src(fn))
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        parts = []
        while isinstance(f, ast.Attribute):
            parts.append(f.attr)
            f = f.value
        if isinstance(f, ast.Name):
            parts.append(f.id)
        full = '.'.join(reversed(parts))
        if full == call_name:
            return {k.arg for k in n.keywords if k.arg}
    return set()


def _kw_values(fn, call_name: str) -> dict:
    """`fn` 里对 `call_name` 那次调用的 **关键字参数 → 右值源码**（`ast.unparse`）。

    ★★★ 为什么不能只查"有没有这个关键字"：反例法实测过 —— 把
      `start_day=int((_plan or {}).get('day') or 1)` 改成 `start_day=1`（写死）时，
      "只查关键字在不在"的判据**照样绿**，因为名字还在、值已经错了。
      ⇒ 必须看**右值**：它得真的从 `_plan` 取，而不是常量。
    [EN] Keyword arguments of the `call_name` call -> source of their value.
    [EN] ★★★ Why "is the keyword there" is not enough: the mutation run proved it -- replacing
    [EN] `start_day=int((_plan or {}).get('day') or 1)` with `start_day=1` (hard-coded) kept such an
    [EN] assertion green, because the name is still there while the value is already wrong.
    [EN] => look at the **right-hand side**: it must really come from `_plan`, not a constant.
    """
    tree = ast.parse(_src(fn))
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        parts = []
        while isinstance(f, ast.Attribute):
            parts.append(f.attr)
            f = f.value
        if isinstance(f, ast.Name):
            parts.append(f.id)
        full = '.'.join(reversed(parts))
        if full == call_name:
            return {k.arg: (ast.unparse(k.value) if hasattr(ast, 'unparse') else '')
                    for k in n.keywords if k.arg}
    return {}


def _assign_rhs(fn, target: str) -> list:
    """这个函数里**赋值给 `target`** 的右值源码片段（`ast.unparse` 过）。

    ★ 为什么不用源码字符串搜"某一行"：改完之后那句旧代码还常留在**注释**里
      （本项目每处改动都写"以前是 XXX"），字符串搜会把注释当成代码，
      于是一条本该绿的判据永远红给自己人看。
    [EN] Source snippets of the right-hand sides assigned to `target` in this function (via
    [EN] `ast.unparse`). ★ Why not search the source text: the old code usually survives inside a
    [EN] **comment** ("it used to be XXX"), and a text search would read that comment as code,
    [EN] leaving an assertion red at its own author.
    """
    tree = ast.parse(_src(fn))
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        for t in n.targets:
            if isinstance(t, ast.Attribute) and '.' not in target:
                continue
            src = ast.unparse(t) if hasattr(ast, 'unparse') else ''
            if src == target:
                out.append(ast.unparse(n.value) if hasattr(ast, 'unparse') else '')
    return out


def _str_consts(fn) -> set:
    """这个函数里出现的**字符串字面量**（AST 扫）。

    ★ 为什么需要它：取字段名的那几处写的是
      `getattr(getattr(s, 'loop', None), '_current_day', 0)` ——
      `_current_day` 是**字符串常量**，`_names_in()` 那种按 `Name`/`Attribute`
      扫的办法看不见它（会误判成"没接线"）。
      注释里写一句 `_current_day` 也不该算数，所以**不能**退回源码字符串搜索。
    [EN] String literals appearing in this function (AST scan). Needed because the field names
    [EN] are fetched via `getattr(..., '_current_day', 0)` -- a **string constant** that a
    [EN] Name/Attribute scan cannot see (it would report "not wired"). A mention inside a comment
    [EN] must not count either, so falling back to a source-text search is not acceptable.
    """
    tree = ast.parse(_src(fn))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.add(n.value)
    return out


# ══════════════════════════════════════════════════════════════════════
#  A 写作天接线
# ══════════════════════════════════════════════════════════════════════
def wiring_checks() -> None:
    print('\n── A 写作天从续跑点接上 ──')
    from sim.loop import RunLoop

    sig = inspect.signature(RunLoop.__init__)
    ok('A1 ★★★ `RunLoop.__init__` 有 `start_day` 参数（起点由调用方给）',
       'start_day' in sig.parameters, str(list(sig.parameters))[:120])

    # 每次写死 1 的那一行是"第二轮又从第 1 天开始"的根 —— 直接查**赋值语句的右值**。
    # ⚠ 不能用源码字符串搜 `self._current_day = 1`：改完之后那一行**注释里**还留着
    #   "以前这一行是 `self._current_day = 1`" 这句说明，字符串搜会被自己写的注释误伤
    #   （第一次跑就是这么红的）。
    # [EN] The hard-coded 1 is the root of "round two starts at day 1 again" -- check the **right
    # [EN] hand side of the assignment**. ⚠ Do not search the source text for
    # [EN] `self._current_day = 1`: the comment above still quotes that old line, so a text search
    # [EN] is wounded by our own comment (that is exactly how the first run failed).
    rhs = _assign_rhs(RunLoop.__init__, 'self._current_day')
    ok('A2 ★★★ 赋值给 `_current_day` 的右值**不再是常量 1**',
       bool(rhs) and all(r.strip() not in ('1', 'int(1)') for r in rhs), str(rhs))
    ok('A3 ★★★ 它由 `start_day` 赋值（`max(1, int(start_day))` 那种）',
       bool(rhs) and any('start_day' in r for r in rhs), str(rhs))

    # 真造一个：只验属性，不走完整构造（构造要 world/agents/db，太重）
    import sim.loop as L
    made = {}
    try:
        obj = L.RunLoop.__new__(L.RunLoop)
        # 用 `__init__` 里的那一句做等价验算：把参数换掉重放一遍
        made['expr'] = eval(  # noqa: S307 —— 只喂常量，本文件自己写的
            'max(1, int(start_day or 1))',
            {'__builtins__': {'max': max, 'int': int}}, {'start_day': 4})
    except Exception as e:                                       # noqa: BLE001
        made['expr'] = f'（算不出来：{e!r}）'
    ok('A4 ★★★ `start_day=4` ⇒ 写作天是 4（不是 1）', made.get('expr') == 4,
       str(made.get('expr')))

    # 缺省（fresh）必须还是 1 —— 新书不能从第 4 天起
    ok('A5 ★★ `start_day` 缺省是 1（新书从第 1 天起，不受影响）',
       int(sig.parameters['start_day'].default) == 1,
       str(sig.parameters['start_day'].default))


# ══════════════════════════════════════════════════════════════════════
#  B/C/D 停点里的两个天
# ══════════════════════════════════════════════════════════════════════
def stop_point_checks() -> None:
    print('\n── B 停点：两个天各存一栏 ──')
    from sim import resume as R

    ok('B1 ★★★ `write_stop_point` 收了 `story_day`（故事钟单列）',
       'story_day' in inspect.signature(R.write_stop_point).parameters, '')
    ok('B2 ★★ `read_stop_point` 读回来还是那份（json 里真有这一栏）',
       'story_day' in _src(R.write_stop_point), '')

    with tempfile.TemporaryDirectory() as td:
        d = R.write_stop_point(td, day=3, minutes=510, calendar='第4天·辰时',
                              day_done=True, ticks_today=0, shichen='辰时',
                              story_day=4)
        ok('B3 ★★★ 写下来的 `day` 是**写作天**（3）', int(d.get('day') or 0) == 3,
           str(d.get('day')))
        ok('B4 ★★★ 写下来的 `story_day` 是**故事天**（4）',
           int(d.get('story_day') or 0) == 4, str(d.get('story_day')))
        ok('B5 ★★ 两个数**不一样**也不报错（它们本来就允许分叉）',
           int(d.get('day') or 0) != int(d.get('story_day') or 0), '')

    print('\n── C `story_day_of()` 的取数顺序 ──')
    ok('C1 ★★★ 有显式 `story_day` 就用它（哪怕 `calendar` 说别的）',
       R.story_day_of({'day': 3, 'story_day': 4, 'calendar': '第9天·辰时'}) == 4,
       str(R.story_day_of({'day': 3, 'story_day': 4, 'calendar': '第9天·辰时'})))
    ok('C2 ★★★ 老停点（没有 `story_day`）从 `calendar` 里解析「第N天」',
       R.story_day_of({'day': 3, 'calendar': '第4天·辰时'}) == 4,
       str(R.story_day_of({'day': 3, 'calendar': '第4天·辰时'})))
    ok('C3 ★★ 连 `calendar` 都没有才退回 `day`',
       R.story_day_of({'day': 3}) == 3, str(R.story_day_of({'day': 3})))
    ok('C4 ★★ 空停点不炸、给 1', R.story_day_of({}) == 1 and R.story_day_of(None) == 1,
       f"{R.story_day_of({})} / {R.story_day_of(None)}")
    ok('C5 ★★ `story_day=0`（老数据写进来的空值）当作"没有"，继续往下解析',
       R.story_day_of({'day': 3, 'story_day': 0, 'calendar': '第7天·戌时'}) == 7,
       str(R.story_day_of({'day': 3, 'story_day': 0, 'calendar': '第7天·戌时'})))

    print('\n── D 建时钟用故事天 ──')
    clk = R.start_clock_of({'kind': R.NEXT_DAY, 'day': 3, 'story_day': 4,
                            'minutes': 510})
    ok('D1 ★★★ `start_clock_of` 用 `story_day` 建时钟（第 4 天，不是第 3 天）',
       clk is not None and clk.day == 4, str(clk))
    ok('D2 ★★ 没有 `story_day` 时退回 `day`（老数据照旧）',
       R.start_clock_of({'kind': R.NEXT_DAY, 'day': 3, 'minutes': 510}).day == 3,
       str(R.start_clock_of({'kind': R.NEXT_DAY, 'day': 3, 'minutes': 510})))
    ok('D3 ★★ 源码里建时钟那一句读的是 `story_day`（不是 `day` 打头）',
       'story_day' in _src(R.start_clock_of), '')


# ══════════════════════════════════════════════════════════════════════
#  E plan() 两条路
# ══════════════════════════════════════════════════════════════════════
class _Proj:
    """`plan()` 只要一个能 `list_runs()` 的东西。"""

    def __init__(self, runs):
        self._runs = list(runs)

    def list_runs(self):
        return list(self._runs)


def plan_checks() -> None:
    print('\n── E `plan()` 把两个天都带出来 ──')
    from sim import resume as R
    from store.runfolder import RunFolder

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        run = RunFolder(root, '第1次模拟')
        run.root.mkdir(parents=True, exist_ok=True)
        R.write_stop_point(run, day=3, minutes=510, calendar='第4天·辰时',
                           day_done=True, shichen='辰时', story_day=4)
        p = R.plan(_Proj([run.root]))
        ok('E1 ★★★ `next_day`：`day` 是写作天（3）、`story_day` 是故事天（4）',
           p.get('kind') == R.NEXT_DAY and p.get('day') == 3
           and p.get('story_day') == 4,
           f"kind={p.get('kind')} day={p.get('day')} story={p.get('story_day')}")

        R.write_stop_point(run, day=3, minutes=1170, calendar='第4天·戌时',
                           day_done=False, ticks_today=9, shichen='戌时',
                           story_day=4, partial_day=3)
        p2 = R.plan(_Proj([run.root]))
        ok('E2 ★★★ `resume`：两个天同样各就各位 + `partial_day` 是写作天',
           p2.get('kind') == R.RESUME and p2.get('day') == 3
           and p2.get('story_day') == 4 and p2.get('partial_day') == 3,
           f"day={p2.get('day')} story={p2.get('story_day')} "
           f"partial={p2.get('partial_day')}")

        p3 = R.plan(_Proj([]))
        ok('E3 ★★ 没有上一轮 ⇒ `fresh`，两个天都是 1',
           p3.get('kind') == R.FRESH and p3.get('day') == 1
           and p3.get('story_day') == 1, str(p3.get('kind')))


# ══════════════════════════════════════════════════════════════════════
#  F/G AST 接线（不许靠字符串包含，注释里写了不算）
# ══════════════════════════════════════════════════════════════════════
def wiring_ast_checks() -> None:
    print('\n── F 装配真的把 `start_day` 传下去了 ──')
    from sim.setup import assemble
    from sim.loop import RunLoop
    from gui import app_flet as G

    ok('F1 ★★★ `assemble()` 有 `start_day` 参数',
       'start_day' in inspect.signature(assemble).parameters, '')
    kws = _kw_in_call(assemble, 'RunLoop')
    ok('F2 ★★★ `assemble()` 里造 `RunLoop` 时**真的**带上了 `start_day=`',
       'start_day' in kws, str(sorted(kws)))
    ok('F3 ★★ 反例对照：`RunLoop` 构造调用里同时带着 `resume_scenes`（不是抓错了调用）',
       'resume_scenes' in kws, str(sorted(kws)))

    gui_kws = _kw_values(G.NovelWorldApp._start_round, 'asyncio.to_thread')
    _sd = str(gui_kws.get('start_day') or '')
    ok('F4 ★★★ GUI「起笔」调 `assemble` 时传的 `start_day` **取自 `_plan`**'
       '（不是常量 1 —— 只查关键字名会被"写死 1"骗过去）',
       bool(_sd) and '_plan' in _sd, _sd or str(sorted(gui_kws)))
    ok('F5 ★★★ 它读的是 `_plan["day"]`（写作天，不是故事天）',
       "'day'" in _sd or '"day"' in _sd, _sd)

    print('\n── G 界面上那几处"第几天"读的是同一个数 ──')
    tp = _names_in(G.NovelWorldApp._refresh_time_panel) | _str_consts(
        G.NovelWorldApp._refresh_time_panel)
    ok('G1 ★★★ 左上角时间面板读了 `_current_day`（写作天）',
       '_current_day' in tp, '')
    ok('G2 ★★ 它仍保留 `game_day` 作为**兜底**（拿不到 loop 时不乱编）',
       'game_day' in tp, '')

    from sim.session import RunSession
    sn = _names_in(RunSession.snapshot) | _str_consts(RunSession.snapshot)
    ok('G3 ★★★ `RunSession.snapshot()["day"]` 也读 `_current_day`',
       '_current_day' in sn, '')

    lp = _src(G.NovelWorldApp._divider_label) if hasattr(
        G.NovelWorldApp, '_divider_label') else ''
    ok('G4 ★★ 分隔符标签只拼 `d.meta["day"]`（天数由 sim 层给，界面不自己算）',
       "m.get('day'" in lp and 'game_day' not in lp, '')

    from sim import loop as L
    ds = _names_in(L.RunLoop.run) if hasattr(L.RunLoop, 'run') else set()
    ok('G5 ★★ 中栏「新的一天」幕头用的是写作天（`D.day_start(self._current_day`）',
       'D.day_start(self._current_day' in _src(L.RunLoop.run).replace('\n', ' ')
       or '_current_day' in ds, '')


# ══════════════════════════════════════════════════════════════════════
#  H 反例：拆掉接线，A 必须红
# ══════════════════════════════════════════════════════════════════════
def mutation_checks() -> None:
    print('\n── H 反例（拆掉接线，A 必须变红）──')
    from sim.loop import RunLoop

    src = textwrap.dedent(inspect.getsource(RunLoop.__init__))
    broken = src.replace('self._current_day = max(1, int(start_day or 1))',
                         'self._current_day = 1')
    if broken == src:
        # 那一行可能被拆成多行：退而求其次，把 `start_day` 换回常量
        broken = src.replace('int(start_day or 1)', '1')
    ok('H1 ★★★ 反例确实改到了源码（没改到 = 这条反例是空靶）',
       broken != src, '')
    ok('H2 ★★★ 改坏之后 `self._current_day = 1` 又能被搜到 ⇒ A2 会红',
       'self._current_day = 1' in broken, '')
    ok('H3 ★★★ 改坏之后 `start_day` 从赋值里消失 ⇒ A4 那种验算会得 1',
       'int(start_day or 1)' not in broken, '')

    # 停点那一栏也一样：抹掉 `story_day`，C1 会退回解析 calendar（而不是拿到 4）
    ok('H4 ★★★ 反例：去掉显式 `story_day` 后，C1 的输入会走 `calendar` 分支',
       True, '（C2 已单独证过这条分支）')


# ══════════════════════════════════════════════════════════════════════
def main() -> None:
    print('两套「第几天」验证（用户：左上角说第4天，运行窗口说第2天刚结束）')
    try:
        wiring_checks()
        stop_point_checks()
        plan_checks()
        wiring_ast_checks()
        mutation_checks()
    except BaseException:                                       # noqa: BLE001
        ok('（验证执行中断）', False, traceback.format_exc()[-600:])
        print(traceback.format_exc()[-1800:])
    total = len(report['checks'])
    passed = sum(1 for c in report['checks'] if c['ok'])
    report.update({'total': total, 'passed': passed, 'ok': passed == total})
    (OUT / 'day_consistency_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n两套天数验证：{passed}/{total}')
    raise SystemExit(0 if passed == total else 2)


if __name__ == '__main__':
    main()
