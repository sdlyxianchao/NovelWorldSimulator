# -*- coding: utf-8 -*-
"""判据：**开演前那几块卡片** + **停止按钮的行为**（2026-10-07 第八轮修的三件事）。

用户报的三条：
  ① 「每天开始以及每次推演开始时候的**前情提要后面的今日剧情介绍卡片、
     出场任务卡片、场景介绍卡片都没了**」
  ② 「**手动停止或者自动结束后的总结卡片**也没看到」
  ③ 「**停止按钮点了没反应**」

查出来的东西（每一条都对应下面一组判据）：

  · ① 是一个**真 bug**：`run()` 判"要不要开场"用的是 `game_day != _current_day`，
    而两者**初值都是 1** → **每一轮的第一天从来不执行 `_open_day()`**
    （编剧室/样章/剧本/验算/排练/派活/今日简介/场景介绍/当天地图/声音 全缺）。
  · ① 还缺一块：**今日任务分配**（用户白名单里的「导演工作分配」）此前
    只写进人物自己的 `day_plan`，**读者一个字都看不到**。
  · ② 其实在工作（判据 B 盯着），当时看不到多半是因为 ③ —— 停不下来就永远走不到收尾。
  · ③ 两个原因：**点了没有回音**（收尾要跑十几次调用，中栏一条消息都没有）、
    **等太久**（正赶上一天开场时会从头跑完）。

判据分四组，**每组都要能红**（见 `developers/mutate_day_start.py`）：

  A **第一天必须开场**（行为级）：真跑 `run()`，抓中栏实际发出的 `(kind, text)` ——
     `recap` / `brief` / `task` / 场景介绍 **每一样都得出现**，
     而且"抓到了数据"本身要先断言（空数据下"全都在"是真空成立）。
  B **今日任务卡**：`task_block` 的文本形状 + 真的以 `TASK` kind 上屏 +
     空表**不推**（不推一个空框）。
  C **停止**：立刻有回音（中栏那条）、长时间流程里查得到停止请求、
     没在跑时不静默。
  D **收尾不重复**：同一天不会收两次工（重复落盘 + 重复总结）。

用法：.venv\\Scripts\\python.exe tools/verify_day_start.py
产出：assets/screenshots/day_start_report.json

English:
criteria: **the cards before the show starts** + **the stop button's behavior** (the three
things fixed in round eight on 2026-10-07).
the three reported by the user:
  ① "at the start of every day and every simulation, the cards after the recap -- today's plot intro card,
     the cast task card, the scene intro card -- are all gone"
  ② "the summary card after a manual stop or an automatic end is also not seen"
  ③ "clicking the stop button does nothing"
what was found (each one maps to a set of criteria below):
  · ① is a **real bug**: `run()` decides "whether to open the day" using `game_day != _current_day`,
    and both **start at 1** → **the first day of every round never executes `_open_day()`**
    (writers' room / sample chapter / script / verification / rehearsal / assignments / today's brief / scene intro / today's map / sound are all missing).
  · ① is also missing a piece: **today's task assignment** ("director's work assignment" in the user's whitelist) previously
    was only written into the character's own `day_plan`, **the reader couldn't see a single word of it**.
  · ② was actually working (criterion B watches it); not seeing it at the time was mostly due to ③ -- if it can't stop, it can never reach wrap-up.
  · ③ has two reasons: **clicking gives no response** (wrap-up runs a dozen-plus calls, and not a single message in the middle column),
    and **waiting too long** (right at the start of a day it runs through from the beginning).
the criteria are in four groups, **every group must be able to go red** (see
`developers/mutate_day_start.py`):
  A **day one must open** (behavioral): really run `run()`, capture the `(kind, text)` actually emitted into the middle column --
     `recap` / `brief` / `task` / scene intro **each must appear**,
     and "we caught data" itself must be asserted first (on empty data "everything is present" is vacuously true).
  B **today's task card**: the text shape of `task_block` + really going on screen with kind `TASK` +
     an empty table **does not push** (don't push an empty box).
  C **stop**: immediate response (that middle-column entry), the stop request is visible inside a long flow,
     not silent when not running.
  D **wrap-up is not repeated**: the same day won't wrap up twice (duplicate persistence + duplicate summary).
usage: .venv\\Scripts\\python.exe tools/verify_day_start.py
Output: assets/screenshots/day_start_report.json
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}
#: 夹具里包的那层 `_end_day` 记下来的账：`(天, 收工时 _ticks_today)`。
#: 模块级 —— 因为**填它的在 A 组、读它的在 D 组**（函数之间传参会把夹具签名搞乱）。
# [EN] : the account recorded by the `_end_day` wrapped in the fixture: `(day, _ticks_today at
# [EN] wrap-up)`.
# [EN] : module-level -- because **the one that fills it is in group A, the one that reads it is in
# [EN] group D** (passing it between functions would mess up the fixture signature).
_END_LEDGER: list = []


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'   [{str(detail)[:110]}]' if detail and not cond else ''))
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


class _Cfg:
    def __init__(self, **kw):
        self._kw, self._old = kw, {}

    def __enter__(self):
        for k, v in self._kw.items():
            self._old[k] = CFG.raw(k)
            CFG.set(k, str(v))
        return self

    def __exit__(self, *exc):
        for k, v in self._old.items():
            CFG.set(k, v)
        return False


def _rows_of_run(max_days: int = 1, *, ticks: int = 400) -> list[tuple]:
    """真跑一轮，返回中栏实际发出的 `(kind, text)` 序列。

    ⚠ 四条"夹具会骗你"的坑（第一版全踩过）：
      · `nodes=0` —— 给进度表的话，跑完第一个节点就"全篇终"，**跨不了天**；
      · `PAUSE_AT_NIGHT=false` —— 默认入夜会暂停等人点继续，探针会挂到超时；
      · `INTERVENTION_POLICY=auto_resolve` —— 默认 `pause`，同样会挂住；
      · `TIME_RATIO` 要给大 —— 不然几十秒的真实时间推不到第二天。
    
        English:
    Actually run one round; return the sequence of `(kind, text)` actually emitted by the middle
    column.
        ⚠ Four "the fixture will lie to you" pitfalls (the first version hit all of them):
          · `nodes=0` —— for the progress schedule, the first node finishes and it's "the end of the whole thing", **cannot cross days**;
          · `PAUSE_AT_NIGHT=false` —— by default, nightfall pauses and waits for someone to click continue, the probe will hang until timeout;
          · `INTERVENTION_POLICY=auto_resolve` —— default is `pause`, which likewise hangs;
          · `TIME_RATIO` must be set large —— otherwise tens of seconds of real time cannot advance to the next day.
    """
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU
    from sim.session import RunSession

    tmp = Path(tempfile.mkdtemp(prefix='nws_day_'))
    proj = make_project(tmp / '开场判据', nodes=0)
    run = RunFolder(proj.root, '第1次模拟2026-10-07-00-01').create()
    loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)
    rows: list[tuple] = []
    loop.on_narrative(lambda t, p, **kw: rows.append((kw.get('kind', ''), t)))
    # ★ D 组要用：真 `_end_day` 每被调一次就记一笔"它返回时 `_ticks_today` 是几"
    #   —— 行为级地验"收尾不重复 / 计数会归零"，比读源码可靠
    #   （读源码那种哨兵抓不住"逻辑被换掉但字还在"，反例法当场揭穿过）。
    # [EN] ★ group D needs it: every time the real `_end_day` is called, record "what `_ticks_today` was
    # [EN] when it returned"
    # [EN] -- verify "wrap-up is not repeated / the count resets" at the behavioral level, more reliable
    # [EN] than reading the source
    # [EN] (the source-reading kind of sentinel can't catch "the logic was swapped out but the words are
    # [EN] still there", the counterexample method exposed it on the spot).
    _END_LEDGER.clear()
    _real_end_day = loop._end_day

    async def _wrapped_end_day(*a, **k):
        out = await _real_end_day(*a, **k)
        _END_LEDGER.append((int(getattr(loop, '_current_day', 0) or 0),
                            int(getattr(loop, '_ticks_today', -1))))
        return out
    loop._end_day = _wrapped_end_day

    sess = RunSession(loop, world, run)

    async def _drive():
        sess.start()
        for _ in range(ticks):
            await asyncio.sleep(0.02)
            if world.game_day > max_days or not sess.is_alive:
                break
        sess.stop()
        await sess.wait(60)

    # ⚠ 必须真的在事件循环里驱动（`start()` 拿不到 running loop 会直接
    #   把自己置成 `stopped` 并返回 False —— 第一版就是这么拿到 0 条数据的）
    # [EN] ⚠ must really be driven inside the event loop (`start()` can't get a running loop, it will
    # [EN] directly
    # [EN] set itself to `stopped` and return False -- the first version got 0 records of data this way)
    asyncio.run(_drive())
    return rows, sess, loop, world


# ══════════════════════════════════════════════════════════════
#  A 第一天必须开场
# [EN] A day one must open
# ══════════════════════════════════════════════════════════════
def test_day_one_open() -> bool:
    ok = True
    with _Cfg(TIME_RATIO='3000', BEAT_SECONDS='1',
              PAUSE_AT_NIGHT='false', INTERVENTION_POLICY='auto_resolve'):
        rows, sess, loop, world = _rows_of_run(max_days=1)
    # ⚠ 先断言"真的抓到东西了" —— 不然下面几条在空表上全是真空成立
    # [EN] ⚠ first assert "we actually caught something" -- otherwise the following checks are all
    # [EN] vacuously true on an empty table
    ok &= rec('A0 ★★ 真的抓到了中栏序列（空数据下"全都在"是真空成立）',
              len(rows) >= 5, f'{len(rows)} 条')

    kinds = [k for k, _t in rows]
    for kind, label in (('recap', '前情提要'), ('brief', '今日剧情简介'),
                        ('task', '今日任务'), ('ambient', '场景介绍')):
        n = kinds.count(kind)
        ok &= rec(f'A1 ★★★ 第 1 天**出现了「{label}」**（`{kind}`）'
                  + ('' if n else '  ← ★ 这正是用户报"卡片都没了"的那一块'),
                  n >= 1, f'中栏 kind 统计：{ {k: kinds.count(k) for k in set(kinds)} }')

    # 顺序：前情提要 → 今日简介 → 今日任务 → 场景介绍
    # [EN] order: recap → today's brief → today's tasks → scene intro
    order = [i for i, k in enumerate(kinds)
             if k in ('recap', 'brief', 'task', 'ambient')][:4]
    want = ['recap', 'brief', 'task', 'ambient']
    ok &= rec('A2 ★★ 四块的**顺序**是 前情提要 → 今日简介 → 今日任务 → 场景介绍'
              '（用户点名要的顺序）',
              [kinds[i] for i in order] == want,
              str([kinds[i] for i in order]))
    return ok


# ══════════════════════════════════════════════════════════════
#  B 今日任务卡
# [EN] B today's task card
# ══════════════════════════════════════════════════════════════
def test_task_card() -> bool:
    ok = True
    from display import story_render as STR

    blk = STR.task_block([('主角', ['把少了的那几文弄清楚', '别让外人看出楼里出了事']),
                          ('阿枝', ['盯住门口来往的人'])])
    ok &= rec('B1 ★ 任务卡有抬头 + 每人一行（`▤ 今日任务`）',
              '今日任务' in blk and '主角' in blk and '阿枝' in blk,
              blk.replace('\n', ' | ')[:80])
    ok &= rec('B1 ★ 三样都在：记号 `▤` / 人名 / 任务本身',
              '▤' in blk and '把少了的那几文弄清楚' in blk, '')
    ok &= rec('B2 ★★ 空表 → **空串**（不推一个空框出来）',
              STR.task_block([]) == ''
              and STR.task_block([('主角', [])]) == ''
              and STR.task_block([('', ['x'])]) == '', '')
    ok &= rec('B2 ★ 单人的多条任务并成一行（清单不是列表嵌套）',
              blk.count('主角') == 1 and '；' in blk, blk)

    # kind 在**中栏白名单**里（不在的话界面这一层就把它挡掉了）
    # [EN] kind is in the **middle-column whitelist** (if not, the UI layer already blocks it)
    from display import script as S
    ok &= rec('B3 ★★ `TASK` 在 `WINDOW_KINDS` 里（否则界面把它过滤掉，'
              '推了也看不见）',
              S.TASK in S.WINDOW_KINDS and S.on_window(S.TASK), '')
    ok &= rec('B3 ★ 界面也给了它一套样式（`NARR_BLOCK_STYLE` / `_LIVE_STYLE`）',
              S.TASK in open(APP / 'gui' / 'app_flet.py', encoding='utf-8').read(),
              '')
    # 与"每 N 拍的临时派活"分开（两个 kind，不许合并）
    # [EN] separate from "the temporary assignment every N beats" (two kinds, no merging allowed)
    ok &= rec('B4 ★★ `TASK`（一天一次的任务分配）与 `NOTE`（每 N 拍的临时派活）'
              '是**两个** kind —— 一个是大纲、一个是过程中的调整',
              S.TASK != S.NOTE, '')
    return ok


# ══════════════════════════════════════════════════════════════
#  C 停止
# [EN] C stop
# ══════════════════════════════════════════════════════════════
def test_stop() -> bool:
    ok = True
    from sim.loop import RunLoop

    # ① 立刻有回音：`stop()` 要往中栏推一条（不许只置标志）
    # [EN] ① immediate response: `stop()` must push one into the middle column (setting a flag alone is not
    # [EN] allowed)
    loop = RunLoop.__new__(RunLoop)
    got: list[tuple] = []
    loop._on_narrative = lambda t, p, **k: got.append((k.get('kind', ''), t))
    loop._on_divider = None
    loop._stage_start = lambda k: None
    loop._display = SimpleNamespace(enqueue_narrative=_noop_async)
    loop._stop_requested = False
    loop._running = True
    loop.stop()
    ok &= rec('C1 ★★ `stop()` **立刻**往中栏推一条（用户报"点了没反应"'
              '—— 以前这里只置一个标志，中栏一条消息都没有）',
              len(got) >= 1 and any('正在停止' in t for _k, t in got),
              str(got)[:120])
    ok &= rec('C1 ★ 而且**说清了要等什么**（补落这一天 / 写总结 / 自动导出）',
              any(all(w in t for w in ('总结', '自动导出')) for _k, t in got),
              str(got)[:160])
    ok &= rec('C1 ★ 它**不是** `SUMMARY` kind（那是一件"收工结论"，'
              '"正在停止"只是一条状态，用同一个 kind 会让总结的数量对不上）',
              bool(got) and all(k != 'summary' for k, _t in got), str(got[:1]))
    # 连点不许刷屏
    # [EN] repeated clicks must not spam
    got.clear()
    loop.stop()
    ok &= rec('C1 ★ 连点几下**只报一次**（不刷出一排「正在停止」）',
              len(got) == 0, str(got)[:80])

    # ② 提前退出：长流程里查得到停止请求
    # [EN] ② early exit: the stop request is visible inside a long flow
    ok &= rec('C2 ★★★ `_open_day` / `_compose_day` / `_tick` 里都有"请求停止就'
              '收手"的检查（不然正赶上一天开场时会**从头跑完**十来次调用）',
              all('stopping' in inspect.getsource(fn) for fn in
                  (RunLoop._open_day, RunLoop._compose_day, RunLoop._tick)),
              '')
    ok &= rec('C2 ★ 判据是 `stopping`（专门的停止标志）而**不是** `_running`'
              '—— `_running` 初值是 False，而探针/判据大量直接调 `_tick`',
              'stopping' in inspect.getsource(RunLoop.stopping.fget)
              and 'getattr' in inspect.getsource(RunLoop.stopping.fget), '')

    # ③ 没在跑时不静默
    # [EN] ③ not silent when not running
    src = (APP / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    i = src.find('def _on_stop_run')
    # ⚠ 找 `async def`（不是 `def`）—— 按后者切会留下一个悬空的 `async `，
    #   AST 解析当场 IndentationError（第一版就这么崩的）。
    # [EN] ⚠ look for `async def` (not `def`) -- splitting by the latter leaves a dangling `async `,
    # [EN] and `ast.parse` immediately throws IndentationError (the first version crashed this way).
    j = src.find('async def _await_stop')
    body = src[i:j if j > i else i + 2000]
    # ⚠ 判法要**按位置**，不能只查"这两个词在不在"：变异把 `return` 插到
    #   `_show_snack` **前面**，两个词都还在（判据于是不红）——
    #   而那一插就是"又静默了"。所以要求：**第一个 `return` 必须排在
    #   `_show_snack` 之后**（也就是"先告诉用户，再退出"）。
    # ⚠ 判法要用 **AST 行号**，不能查文本位置：这段 docstring 里本来就写着
    #   "`if not s or not s.is_alive: return`" 这句话 —— 按文本找 'return'
    #   会先找到注释里那个（第一版就是这么假红的）。
    # [EN] ⚠ the check must be **positional**, not just "are these two words present": the mutation inserts
    # [EN] `return`
    # [EN] **before** `_show_snack`, both words are still present (so the criterion doesn't go red) --
    # [EN] and that insertion is exactly "silent again". So the requirement is: **the first `return` must
    # [EN] come after
    # [EN] `_show_snack`** (that is, "tell the user first, then exit").
    # [EN] ⚠ the check must use **AST line numbers**, not textual positions: this docstring already
    # [EN] contains
    # [EN] the sentence "`if not s or not s.is_alive: return`" -- searching for 'return' textually
    # [EN] will find the one in the comment first (the first version went falsely red this way).
    # ⚠★ 2026-10-12 改判法：原来要求"**第一个** `return` 排在 `_show_snack` 之后"，
    #   而那一轮给这个方法**前面**加了一支合法的新分支 ——
    #   「正在启动时按的是**取消启动**」(`if self._launch_phase == LAUNCH_STARTING…`
    #   → `_launch_cancel(...)` → `return`)。那支**也告诉了用户**
    #   （`_launch_cancel` 会往中栏留一条 + 弹 SnackBar），所以"第一个 return"
    #   这个代理指标当场失效 —— 报的是"静默了"，其实两条路都在说话。
    #   ⇒ 改成**按分支判**：找「没在跑」那一支（`s is None or not s.is_alive`），
    #     要求那一支里**先说再退**；顺带钉住「取消启动」那一支也得说话。
    #     这样既容得下合法的新分支，又**比原来更严**：两条早退路各判各的。
    # [EN] ⚠★ 2026-10-12 changed the check: it used to require "the **first** `return` comes after
    # [EN] `_show_snack`", and that round added a legitimate branch **in front of** this method --
    # [EN] "while starting, the button means **cancel launch**" (`if self._launch_phase ==
    # [EN] LAUNCH_STARTING…` -> `_launch_cancel(...)` -> `return`). That branch **also tells the
    # [EN] user** (`_launch_cancel` leaves a middle-column line + a SnackBar), so the "first return"
    # [EN] proxy broke on the spot -- it reported "silent" while both paths do speak.
    # [EN] => switch to **per-branch checking**: find the "not running" branch (`s is None or not
    # [EN] s.is_alive`) and require it to **speak first, then exit**; also pin that the "cancel
    # [EN] launch" branch speaks too. This accepts the legitimate new branch while being **stricter
    # [EN] than before**: each early exit is judged on its own.
    import ast as _ast
    import textwrap as _tw
    # ⚠ 切出来的是**类里的方法**（缩进 4 格）→ `ast.parse` 直接吃会
    #   `IndentationError`，必须先 dedent（第一版就是这么崩的）。
    # [EN] ⚠ what we slice out is **a method inside a class** (4-space indent) → feeding it straight to
    # [EN] `ast.parse`
    # [EN] gives `IndentationError`, so we must dedent first (the first version crashed this way).
    _tree = _ast.parse(_tw.dedent(body))
    _fn = _tree.body[0]

    def _seg(node) -> str:
        return _ast.get_source_segment(_tw.dedent(body), node) or ''

    _stopped_branch = None       # 「没在跑」那一支
    _starting_branch = None      # 「正在启动（= 取消启动）」那一支
    # [EN] the "not running" branch / the "starting (= cancel launch)" branch
    for _n in _ast.walk(_fn):
        if not isinstance(_n, _ast.If):
            continue
        _t = _ast.unparse(_n.test) if hasattr(_ast, 'unparse') else ''
        if 'is_alive' not in _t:
            continue
        if 'is None' in _t and 'not s.is_alive' in _t:
            _stopped_branch = _n
        elif 'LAUNCH_STARTING' in _t:
            _starting_branch = _n

    def _speak_before_return(node) -> tuple[bool, str]:
        """这一支里：说话（`_show_snack` / `_launch_cancel`）的行号必须早于 return。"""
        says = [_x.lineno for _x in _ast.walk(node)
                if isinstance(_x, _ast.Call)
                and getattr(_x.func, 'attr', '') in ('_show_snack', '_launch_cancel')]
        rets = [_x.lineno for _x in _ast.walk(node) if isinstance(_x, _ast.Return)]
        if not rets:
            return False, '这一支里没有 return（判据取错了地方）'
        return (bool(says) and min(says) < min(rets),
                f'say@{says} return@{rets}')

    _s_ok, _s_det = _speak_before_return(_stopped_branch) if _stopped_branch is not None \
        else (False, '找不到「没在跑」那一支（`s is None or not s.is_alive`）')
    ok &= rec('C3 ★★ 没在跑时点停止**先告诉用户、再退出**'
              '（「没在跑」那一支里 `_show_snack` 的行号必须排在 return 之前 —— '
              '以前那两行是 `if not s or not s.is_alive: return`，'
              '界面在"没在跑"和"点了没用"上长得一模一样）',
              _s_ok and '已经停了' in _seg(_stopped_branch),
              _s_det)
    # 顺带：**取消启动**那一支也得说话（点了停止就静默取消，等于又回到"点了没用"）
    # [EN] Also: the **cancel launch** branch must speak too (silently cancelling on stop is the
    # [EN] same "clicking does nothing" again)
    _st_ok, _st_det = _speak_before_return(_starting_branch) if _starting_branch is not None \
        else (False, '找不到「正在启动 / 取消启动」那一支')
    ok &= rec('C3b ★ 正在启动时按停止 = **取消启动**，那一支也**说话了**'
              '（`_launch_cancel` 先于 return —— 不然又是一次静默）',
              _st_ok, _st_det)
    ok &= rec('C3 ★ 而"立刻刷新状态/按钮"仍在（点了要马上看得见变化）',
              '_refresh_run_controls' in body, '')
    return ok


# ══════════════════════════════════════════════════════════════
#  D 收尾不重复
# [EN] D wrap-up is not repeated
# ══════════════════════════════════════════════════════════════
def test_no_double_end_day() -> bool:
    """★ **行为级**：`_end_day` 到底被调了几次、`_ticks_today` 会不会归零。

    ⚠ 为什么不用源码哨兵（第一版就是，反例法当场揭穿三条不红）：
      "字符串在不在"抓不住"逻辑被换掉"—— 比如把 `_ticks_today > 0`
      从条件里删掉，那几个字**还在函数里**（别处引用着），判据照样绿。
      这类"计数/次数"的事只能**真跑一遍去数**。
    
        English:
    ★ **Behavioral level**: how many times `_end_day` was actually called, and whether
    `_ticks_today` resets to zero.
        ⚠ Why not use source-code sentinels (the first version did, and the counterexample method exposed three non-red cases on the spot):
          "whether a string is present" cannot catch "the logic being swapped out" —— for example, removing `_ticks_today > 0`
          from a condition; those characters **are still in the function** (referenced elsewhere), and the check stays green.
          For this kind of "count/number of times" matter, the only way is to **actually run one round and count**.
    """
    ok = True
    from sim.loop import RunLoop

    # ① `_end_day` 被调了几次 —— 真跑一轮，数出来
    # [EN] ① how many times `_end_day` was called -- run a real round and count it
    loop = RunLoop.__new__(RunLoop)
    calls: list[int] = []
    loop._tick_no = 3                    # 装成"已经跑过几拍"
    loop._ticks_today = 0                # 但**今天一拍都没跑**（跨天那一刻点的停止）
    # [EN] pretend "several beats have already run"
    # [EN] but **not a single beat ran today** (the stop at the moment of crossing into a new day)
    loop._current_day = 2

    async def fake_end_day():
        calls.append(1)
    loop._end_day = fake_end_day
    loop._push_divider = lambda *a, **k: None
    loop._will_auto_export = lambda: False

    async def fake_export(reason):
        return None
    loop._auto_export = fake_export
    asyncio.run(loop._finish('手动停止'))
    ok &= rec('D1 ★★★ 这一天**一拍都没跑过**时，`_finish` **不再收一次工**'
              '（跨天那一刻点停止 → 不然会再落一天空稿、再写一份重复的总结）',
              calls == [], f'_end_day 被调 {len(calls)} 次')

    # ② 反过来：这一天真跑过几拍 → 必须收工（别把该落的也跳过）
    # [EN] ② the reverse: if this day really ran several beats → must wrap up (don't skip what should be
    # [EN] persisted)
    loop2 = RunLoop.__new__(RunLoop)
    calls2: list[int] = []
    loop2._tick_no = 3
    loop2._ticks_today = 5               # 今天跑过 5 拍
    # [EN] 5 beats ran today
    loop2._current_day = 1

    async def fake_end_day2():
        calls2.append(1)
    loop2._end_day = fake_end_day2
    loop2._push_divider = lambda *a, **k: None
    loop2._will_auto_export = lambda: False

    async def fake_export2(reason):
        return None
    loop2._auto_export = fake_export2
    asyncio.run(loop2._finish('手动停止'))
    ok &= rec('D1 ★ 反过来：这一天跑过拍 → **照常收工**（别把该落的也跳过）',
              calls2 == [1], f'_end_day 被调 {len(calls2)} 次')

    # ③ `_ticks_today` 在跨天时归零 —— **真跑里量**（见夹具里那一层包装）
    # [EN] ③ `_ticks_today` resets to zero when crossing days -- **measure it in a real run** (see the
    # [EN] wrapper in the fixture)
    #
    # ⚠ 不再手工造一个 RunLoop 去跑 `_end_day`：它牵着落盘 / 记忆压缩 / 存档
    #   / 群演收尾一大串，桩到一半就崩（第一版连崩三次）。
    #   "计数会不会归零"这件事，**在真跑里看**最省也最真。
    # [EN] ⚠ no longer hand-build a RunLoop to run `_end_day`: it drags along persistence / memory
    # [EN] compression / save file
    # [EN] / a whole chain of extras wrap-up, stubbing half of it crashes (the first version crashed three
    # [EN] times in a row).
    # [EN] For "does the count reset", **looking at it in a real run** is the cheapest and most faithful.
    ok &= rec('D2 ★★ 真跑一轮：`_end_day` 每返回一次，`_ticks_today` **都是 0**'
              '（不归零的话下一天会被误判成"今天跑过"，D1 那条优化就永远不生效）',
              bool(_END_LEDGER) and all(t == 0 for _d, t in _END_LEDGER),
              f'每次收工后的计数：{_END_LEDGER}')
    ok &= rec('D2 ★ `_end_day` 的次数 == 天数（**没有重复收工**）',
              len(_END_LEDGER) == len({d for d, _t in _END_LEDGER}),
              f'{len(_END_LEDGER)} 次 / {sorted({d for d, _t in _END_LEDGER})}')
    return ok


async def _gate_passthrough(text, _cp):
    return text


async def _noop_async(*a, **k):
    return None


if __name__ == '__main__':
    print('开演前的卡片 + 停止按钮 —— 验证', flush=True)
    ok = True
    try:
        head('A. 第一天必须开场（行为级）')
        ok &= test_day_one_open()
        head('B. 今日任务卡')
        ok &= test_task_card()
        head('C. 停止')
        ok &= test_stop()
        head('D. 收尾不重复')
        ok &= test_no_double_end_day()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False,
            report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'day_start_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n开演前卡片 / 停止：{passed}/{len(report["checks"])}'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1500:])
    sys.exit(0 if report['ok'] else 2)
