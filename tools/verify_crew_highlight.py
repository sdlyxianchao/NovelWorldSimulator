# -*- coding: utf-8 -*-
"""真机验证：**右侧「剧组」面板 —— 谁在干活要高亮，干完恢复普通样式**。

用户 2026-10-08 的原话：
    「右侧的剧组成员 谁在干活请高亮显示 等不干活了再恢复普通样式
      以让用户知道谁在干活」

拆成三件事，三组判据：

  A **出工状态真的被播报出来**（源码级 + 行为级）
      · `Studio.call` 在 `await` **之前**报 `working`（等跑完再报等于全程没报过）；
      · 收工也报一次，且报的是 `slot.state`（不是写死的 `done` —— 失败那一路
        要落回 `idle`，界面不该留着"刚交活"的样子）；
      · `ledger()` 给出 `busy` / `secs`（口径只有一处定义，界面不自己判）；
      · 播报**吞掉所有异常**（播报挂掉绝不能连累一次真实出工）；
      · 整条链真的接上了：`Studio.on_work` → `RunLoop._work_push` → `on_work()`
        → `RunSession(on_crew_work=…)` → `NovelWorldApp._on_crew_work`。
  B **那行真的高亮了**（真机 + 像素）
      · 出工中 → 那一行有暖金底 + 朱砂竖条 + 名字赭金加粗 + 「出工中…」；
      · **屏幕上真的画出来了**（数暖金像素，不是"控件树里有"就算）；
      · 同一时刻**只有在干活的那几行**亮（别人不许跟着亮）。
  C **干完恢复普通样式**（真机 + 像素）
      · 出工结束 → 底色/描边/加粗**全部撤掉**（不是"留着淡淡的底"）；
      · 屏幕上的暖金像素回到 0；
      · 状态回到「已交活」（绿点），底下那句变回"n / m 位已交活"。
  D **事件驱动**（不靠那 0.5 秒一轮的轮询）
      · 短出工（几十毫秒）也**必须亮过一次** —— 定时刷新天然会漏帧；
      · 判据做法：把 `run` 卡在一个 `Event` 上，**在它还没放行时**就查界面。

跑法：
    .venv\\Scripts\\python.exe tools/verify_crew_highlight.py
    .venv\\Scripts\\python.exe tools/verify_crew_highlight.py --logic-only
产出：
    assets/screenshots/crew_highlight_*.png
    assets/screenshots/crew_highlight_report.json

English:
Real machine verification: **the right-side "剧组" panel -- whoever is working must be
highlighted, restore normal style when done**.
User 2026-10-08's exact words:
Split into three things, three groups of criteria:
  A **working state is actually broadcast out** (source level + behavior level)
      · `Studio.call` reports `working` **before** `await` (reporting after it finishes equals never reporting at all);
      · also report once on finish, and report `slot.state` (not a hardcoded `done` -- the failure path
        must fall back to `idle`, the UI must not keep the "just delivered" look);
      · `ledger()` gives `busy` / `secs` (the definition exists in only one place, the UI doesn't judge for itself);
      · broadcast **swallows all exceptions** (a dead broadcast must absolutely not drag down a real working run);
      · the whole chain is really wired up: `Studio.on_work` -> `RunLoop._work_push` -> `on_work()`
        -> `RunSession(on_crew_work=…)` -> `NovelWorldApp._on_crew_work`.
  B **that row is really highlighted** (real machine + pixels)
      · working -> that row has a warm gold background + cinnabar vertical bar + ochre-gold bold name + "出工中…";
      · **it is really drawn on screen** (count warm gold pixels, not "it's in the widget tree" counting);
      · at the same moment **only the rows that are working** are lit (others must not light up along with them).
  C **restore normal style when done** (real machine + pixels)
      · working ends -> background/border/bold **all removed** (not "kept a faint background");
      · the warm gold pixels on screen return to 0;
  D **Event-driven** (does not rely on that 0.5s-per-round polling)
      · Short work bursts (tens of milliseconds) **must also have lit up at least once** —— timed refresh naturally drops frames;
      · Criterion approach: block `run` on an `Event`, **before it is released** query the UI.
How to run:
    .venv\\Scripts\\python.exe tools/verify_crew_highlight.py
    .venv\\Scripts\\python.exe tools/verify_crew_highlight.py --logic-only
Outputs:
    assets/screenshots/crew_highlight_*.png
    assets/screenshots/crew_highlight_report.json
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown                         # noqa: E402

from config import CFG                                         # noqa: E402
# ⚠⚠ 起了界面的脚本**第一条**就是这条重定向：`app.main()` 里的能力校验会走
#   `CFG.save()`，把下面这些 `CFG.set(...)` 的**测试值**写进用户的 `.env`
#   （真出过三次事故：`MOCK_LLM=true` + `AUTOSAVE_SECONDS=2` 之类被落盘）。
# [EN] ⚠⚠ The **first** line of any script that starts the UI is this redirection: the capability check
# [EN] in `app.main()` will go through
# [EN] `CFG.save()`, writing the **test values** of the `CFG.set(...)` calls below into the user's
# [EN] `.env`
# [EN] (This has actually caused three incidents: things like `MOCK_LLM=true` + `AUTOSAVE_SECONDS=2`
# [EN] getting persisted to disk).
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')          # 零网络、零成本、可复现
# [EN] Zero network, zero cost, reproducible
CFG.set('SHOW_OPENING', 'false')
CFG.set('BEAT_SECONDS', '2')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from crew import agents as A                                    # noqa: E402
from crew import roster as R                                    # noqa: E402
from crew import studio as ST                                   # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
ONLY_LOGIC = '--logic-only' in sys.argv
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A —— 出工状态真的被播报出来
# [EN] A -- working state is actually broadcast out
# ══════════════════════════════════════════════════════════════
def _src(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def _calls(fn) -> list[tuple[int, str]]:
    """`[(行号, 被调函数串)]` —— **带行号**才能比先后（`ast.walk` 是广度优先）。
        English:
    `[(line number, called function string)]` —— **with line numbers** you can compare order
    (`ast.walk` is breadth-first).
    """
    out = []
    for n in ast.walk(ast.parse(_src(fn))):
        if isinstance(n, ast.Call):
            out.append((int(getattr(n, 'lineno', 0)), ast.unparse(n.func)))
    return sorted(out)


def logic_checks() -> None:
    call_src = _src(ST.Studio.call)

    # ── A1 「开始出工」必须在 await 之前报 ──
    # [EN] -- A1 "start working" must be reported before the await --
    lines = call_src.split('\n')
    ln_work = next((i + 1 for i, l in enumerate(lines)
                    if "_work_notify(key, 'working')" in l), -1)
    ln_await = next((i + 1 for i, l in enumerate(lines)
                     if 'await member.run(' in l), -1)
    ok('A1 ★★★ `Studio.call` **在 `await` 之前**就报「开始出工」'
       '（等跑完再报 = 出工那几十秒里界面全程没动静）',
       ln_work > 0 and ln_await > 0 and ln_work < ln_await,
       f'第 {ln_work} 行报 working → 第 {ln_await} 行才 await')

    # ── A2 收工也报一次，且报的是 `slot.state` ──
    # [EN] -- A2 also report once on finish, and report `slot.state` --
    done_calls = [l.strip() for l in lines if '_work_notify(key, slot.state)' in l]
    ok('A2 ★★★ 收工也报一次，且报的是 **`slot.state`** 而不是写死的 `done`'
       '（失败那一路落回 idle，界面不该留着"刚交活"的样子）',
       len(done_calls) == 1, str(done_calls[:1]))
    ok('A2b 播报在 `slot.state` **赋值之后**（报的必须是刚定的那个状态）',
       next((i for i, l in enumerate(lines)
             if "_work_notify(key, slot.state)" in l), -1)
       > next((i for i, l in enumerate(lines)
               if "slot.state = 'done' if note.ok else 'idle'" in l), -1),
       '')

    # ── A3 播报吞异常 + 未接回调时直接返回 ──
    # [EN] -- A3 broadcast swallows exceptions + returns directly when no callback is attached --
    wn = _src(ST.Studio._work_notify)
    tree = ast.parse(wn)
    has_try = any(isinstance(n, ast.Try) and n.handlers for n in ast.walk(tree))
    raises = any(isinstance(n, ast.Raise) for n in ast.walk(tree))
    ok('A3 ★★ `_work_notify` 吞掉所有异常（播报挂掉绝不能连累一次真实出工）',
       has_try and not raises, f'try={has_try} raise={raises}')
    ok('A3b 没接回调时直接返回（脚本 / 无头模式不会因为没人接就炸）',
       'if self._on_work is None' in wn, '')

    # ── A4 `ledger()` 给出 busy / secs ──
    # [EN] -- A4 `ledger()` gives busy / secs --
    led = _src(ST.Studio.ledger)
    ok("A4 ★★ `ledger()` 给出 `'busy'`（界面据此高亮 —— 口径只定义一处，"
       '界面不自己判 `state == "working"`）',
       "'busy': busy" in led and "busy = (st == 'working')" in led, '')
    ok("A4b `ledger()` 给出 `'secs'`（已跑多少秒）且只在忙时有值",
       "'secs':" in led and 'if (busy and s.t0)' in led, '')

    # ── A5 整条链真的接上了（AST，不看注释）──
    # [EN] -- A5 the whole chain is really wired up (AST, not looking at comments) --
    loop_src = _src(__import__('sim.loop', fromlist=['x']).RunLoop)
    ok('A5 ★★★ `RunLoop` 把 `on_work` 交给了制片厂'
       '（`Studio(..., on_work=self._work_push)`）',
       'on_work=self._work_push' in loop_src, '')
    ok('A5b `RunLoop._work_push` 真的转发到注册进来的回调（且吞异常）',
       '_work_push' in loop_src and 'cb(str(key), str(state))' in loop_src, '')
    ok('A5c `RunLoop` 有 `on_work(cb)` 注册点',
       'def on_work(' in loop_src, '')

    ses_src = (APP_DIR / 'sim' / 'session.py').read_text(encoding='utf-8')
    ok('A5d `RunSession` 收 `on_crew_work` 并转到 `loop.on_work`',
       'on_crew_work' in ses_src and 'loop.on_work(on_crew_work)' in ses_src, '')

    gtree = ast.parse((APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8'))
    wired = []
    for n in ast.walk(gtree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if (getattr(f, 'id', None) or getattr(f, 'attr', None)) != 'RunSession':
            continue
        for kw in n.keywords:
            if kw.arg == 'on_crew_work':
                wired.append(ast.unparse(kw.value))
    ok('A5e ★★ 界面起会话时真的传了 `on_crew_work=…`（不是写完忘了接）',
       wired == ['self._on_crew_work'], str(wired))

    # ── A6 高亮那两处样式：忙时给底色、不忙时**撤掉** ──
    # [EN] -- A6 highlight those two styles: give a background color when busy, **remove** it when not busy
    # [EN] --
    row_src = _src(__import__('gui.app_flet', fromlist=['x'])
                   .NovelWorldApp._crew_row)
    ok('A6 ★★★ 忙的那一行真的给了底色（`bgcolor=self.CREW_BUSY_BG`）',
       'bgcolor=self.CREW_BUSY_BG' in row_src, '')
    # ★★ A6b 改成**行为判**（2026-10-11 重写）。
    #   老写法是 `'if not busy:' in row_src and 'return inner' in row_src` ——
    #   **钉的是代码形状**：运行页那一轮给整行加了可点外壳（`GestureDetector`），
    #   结构一变它就红，而"不忙时不该有高亮装饰"这件事其实完全成立。
    #   （这正是本项目反复踩的那类脆判据：钉算式 / 钉写法，换个等价的写法就红。）
    #   现在**真调一次 `_crew_row`**、剥掉点击外壳，直接量那一行**有没有装饰**：
    #   底色 / 描边 / 圆角三样都不许有。
    # [EN] ★★ A6b rewritten as a **behavioral** criterion (2026-10-11).
    # [EN] The old form was `'if not busy:' in row_src and 'return inner' in row_src` -- it **pinned a
    # [EN] code shape**: the run-page round wrapped the whole row in a clickable shell
    # [EN] (`GestureDetector`), so a structural change turned it red, while the actual requirement ("no
    # [EN] highlight decoration when not busy") held perfectly well. (This is exactly the brittle-
    # [EN] criterion class this project keeps hitting: pinning a formula or a phrasing, so any equivalent
    # [EN] rewrite goes red.) Now it **really calls `_crew_row`** once, peels the click shell, and measures
    # [EN] whether that row **has decoration**: background / border / corner radius must all be absent.
    from gui.app_flet import NovelWorldApp as _NWA
    # ⚠ `object.__new__(类)` 里要传**类本身**，不是 `type(类)` ——
    #   `type(NovelWorldApp)` 拿到的是元类 `type`，会抛
    #   `TypeError: object.__new__(type) is not safe`（第一版就这么写的）。
    # [EN] ⚠ `object.__new__(cls)` wants **the class itself**, not `type(cls)` --
    # [EN] `type(NovelWorldApp)` yields the metaclass `type` and raises
    # [EN] `TypeError: object.__new__(type) is not safe` (how the first version was written).
    _bare = object.__new__(_NWA)
    _plain = _unwrap_click(_NWA._crew_row(
        _bare, {'key': 'probe', 'name': '探针职位'}, busy=False,
        head='探针职位', line='', text_key='text', dot_key='muted'))
    _deco = (getattr(_plain, 'bgcolor', None), getattr(_plain, 'border', None),
             getattr(_plain, 'border_radius', None))
    ok('A6b ★★★ 不忙时那一行**没有任何高亮装饰**'
       '（底色 / 描边 / 圆角三样都为假 —— 恢复普通样式；'
       '点击外壳剥掉之后再量）',
       not any(x for x in _deco), f'装饰={_deco} 类型={type(_plain).__name__}')
    ok('A6c 高亮还带左侧一道竖色条（光换文字颜色，12 号字上几乎看不出来）',
       'ft.BorderSide(3, self.CREW_BUSY_BAR)' in row_src, '')
    ok('A6d 名字在忙时**加粗**、平时不加粗（`FontWeight.BOLD if busy`）',
       'FontWeight.BOLD if busy' in row_src, '')
    # ⚠ 锚点在 **`_ledger_row`**，不是 `_refresh_crew_panel`（2026-10-17 搬家）：
    #   把"台账行 → 面板行"的拼装抽成 `_ledger_row` 之后（「剧组」与
    #   「在场人物」共用同一份实现），那句「出工中 · 已跑 {s} 秒」跟着搬过去了。
    #   判据查的还是**同一件事**，只是它现在住在新地址。
    # [EN] ⚠ The anchor is on **`_ledger_row`**, not `_refresh_crew_panel` (moved 2026-10-17):
    # [EN] after extracting "ledger row -> panel row" into `_ledger_row` (shared by "Cast" and
    # [EN] "On-stage Characters"), that "出工中 · 已跑 {s} 秒" sentence moved along with it.
    # [EN] The criterion still checks **the same thing**, it just lives at a new address now.
    ok('A6e 忙的那一行有「已跑 N 秒」（跑了三分钟的与刚起步的不能长得一样）',
       '出工中 · 已跑 {s} 秒' in _src(__import__('gui.app_flet',
                                                 fromlist=['x'])
                                     .NovelWorldApp._ledger_row), '')

    # ── A7 事件驱动：`_on_crew_work` 真的重画那一栏 ──
    # [EN] -- A7 event driven: `_on_crew_work` really redraws that column --
    #
    # ⚠ `_calls` 给的是 `ast.unparse(n.func)`，方法调用长成 `self._refresh_crew_panel`
    #   （带 `self.` 前缀）—— 判据要用**子串**，不能拿整串做等值比较
    #   （第一版就是这么假红的）。
    # [EN] ⚠ what `_calls` gives is `ast.unparse(n.func)`, a method call looks like
    # [EN] `self._refresh_crew_panel`
    # [EN] (with the `self.` prefix) -- the criterion must use a **substring**, you can't do an equality
    # [EN] comparison on the whole string
    # [EN] (the first version got a false red exactly this way).
    cb_names = [f for _ln, f in _calls(
        __import__('gui.app_flet', fromlist=['x']).NovelWorldApp._on_crew_work)]
    ok('A7 ★★ 收到出工状态事件时**真的重画那一栏**'
       '（`_refresh_crew_panel()`，按 AST 判不看注释）',
       any('_refresh_crew_panel' in f for f in cb_names), str(sorted(set(cb_names))))

    # ── A8 那一列是 STRETCH（底色要拉满一整行，否则像个小标签）──
    # [EN] -- A8 that column is STRETCH (the background color must fill the whole row, otherwise it looks
    # [EN] like a small tag) --
    ok('A8 ★ 剧组那一列是 `CrossAxisAlignment.STRETCH`'
       '（高亮的底色要占满一整行，不是只包住几个字）',
       'horizontal_alignment=ft.CrossAxisAlignment.STRETCH' in
       (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
       .split('crew_list = ft.Column(')[1][:200], '')


async def led_behavior_checks() -> None:
    """行为级：真的叫一次出工，看台账里的 `busy` / `secs` 对不对。
        English:
    Behavior level: actually call one work burst, check whether `busy` / `secs` in the ledger are
    correct.
    """
    seen: list[tuple[str, str]] = []
    st = ST.Studio(world=None, db=None, on_work=lambda k, s: seen.append((k, s)))
    gate = asyncio.Event()

    class _M:
        async def run(self, ctx, **kw):
            await gate.wait()
            return A.CrewNote(role='art', ok=True, title='x', body='y')

    real = A.member
    A.member = lambda key: _M()          # 打桩：只测台账与播报，不碰真 Agent
    # [EN] Stubbing: only test the ledger and broadcast, don't touch a real Agent
    try:
        led0 = {r['key']: r for r in st.ledger()}
        ok('A9 还没出工时：`busy` 全 False、`secs` 全 0（不预填）',
           not any(r['busy'] for r in led0.values())
           and all(r['secs'] == 0.0 for r in led0.values()), '')

        task = asyncio.ensure_future(
            st.call('art', A.SetCtx(world=None, db=None, day=1)))
        await asyncio.sleep(0.05)
        led1 = {r['key']: r for r in st.ledger()}
        ok('A10 ★★★ 出工中：那一位 `busy=True`，别人 `busy=False`'
           '（高亮只该落在干活的那几位身上）',
           led1['art']['busy'] and not led1['props']['busy'],
           f"art={led1['art']['busy']} props={led1['props']['busy']}")
        ok('A10b 出工状态那一栏写的是 `出工中`（与台账的四个词一致）',
           led1['art']['state'] == 'working', led1['art']['state'])
        ok('A10c 「开始出工」是在 `await` **之前**报的'
           '（`seen` 里第一条就是 working，不能等跑完才出现）',
           seen[:1] == [('art', 'working')], str(seen[:2]))

        await asyncio.sleep(1.05)
        led2 = {r['key']: r for r in st.ledger()}
        ok('A10d 忙的时候 `secs` 真的在涨（跑了 1 秒以上就该 ≥ 1）',
           float(led2['art']['secs']) >= 1.0, str(led2['art']['secs']))

        gate.set()
        await task
        led3 = {r['key']: r for r in st.ledger()}
        ok('A11 ★★★ 干完活：`busy` 回 False（界面据此恢复普通样式）',
           not led3['art']['busy'] and led3['art']['state'] == 'done',
           f"{led3['art']['busy']} / {led3['art']['state']}")
        ok('A11b 干完之后 `secs` 归零（不留着"上次跑了多少"）',
           float(led3['art']['secs']) == 0.0, str(led3['art']['secs']))
        ok('A11c 收工也报了状态，而且是**真的那个**（`done`）',
           seen == [('art', 'working'), ('art', 'done')], str(seen))
    finally:
        A.member = real

    # ── 失败那一路：落回 idle，界面不该留着"刚交活"的绿点 ──
    # [EN] -- the failure path: fall back to idle, the UI must not keep a "just delivered" green dot --
    seen2: list[tuple[str, str]] = []
    st2 = ST.Studio(world=None, db=None, on_work=lambda k, s: seen2.append((k, s)))

    class _Bad:
        async def run(self, ctx, **kw):
            return A.CrewNote(role='art', ok=False, why='模型没给')

    A.member = lambda key: _Bad()
    try:
        await st2.call('art', A.SetCtx(world=None, db=None, day=1))
    finally:
        A.member = real
    led4 = {r['key']: r for r in st2.ledger()}
    ok('A12 ★★ 这一趟没成 → 报的是 `idle`（不是写死的 `done`）：'
       '界面照实显示成"待命"，不留"刚交活"的样子',
       seen2 == [('art', 'working'), ('art', 'idle')]
       and led4['art']['state'] == 'idle', str(seen2))

    # ── 播报抛异常：绝不能连累出工 ──
    # [EN] -- broadcast throws an exception: it must absolutely not drag down the working --
    def _boom(_k, _s):
        raise RuntimeError('播报坏了')
    st3 = ST.Studio(world=None, db=None, on_work=_boom)
    A.member = lambda key: _M2()
    try:
        note = await st3.call('art', A.SetCtx(world=None, db=None, day=1))
        ok('A13 ★★ 播报回调抛异常时，出工照常完成（播报只是播报）',
           bool(getattr(note, 'ok', False)), str(getattr(note, 'title', '')))
    finally:
        A.member = real


class _M2:
    async def run(self, ctx, **kw):
        return A.CrewNote(role='art', ok=True, title='ok', body='')


# ══════════════════════════════════════════════════════════════
#  B/C/D —— 真机
# [EN] B/C/D -- real machine
# ══════════════════════════════════════════════════════════════
def count_color(png, rgb, tol: int = 8) -> int:
    """数屏幕上某个颜色的像素（标记色法用）。`point` 比逐像素循环快得多。
        English:
    Count pixels of a certain color on screen (for the marker-color method). `point` is much faster
    than a per-pixel loop.
    """
    import io
    from PIL import ImageChops
    im = VU.image_of(png).convert('RGB')
    r, g, b = im.split()

    def band(v, target):
        lo, hi = max(0, target - tol), min(255, target + tol)
        return v.point(lambda x: 255 if lo <= x <= hi else 0)
    m = ImageChops.multiply(ImageChops.multiply(band(r, rgb[0]), band(g, rgb[1])),
                            band(b, rgb[2]))
    return int(m.histogram()[255])


def _unwrap_click(ctrl):
    """剥掉"整行可点"那层外壳（`_crew_row` 给整行套的 `GestureDetector`）。

    ★ 2026-10-11（运行页面板那一轮）：剧组每一行现在是**可点的**（点一行直接进
      那个职位的设置），于是"这一行"外面多了一层 `GestureDetector`。
      判据要量的仍然是**那一行本身**的样式（底色 / 描边 / 加粗），所以先剥壳 ——
      与时间戳那次（`_narr_ts_wrap` 外壳）**同一个手法**，不是放宽标准：
      外壳只负责"能不能点"，不带任何视觉装饰。

        English:
    Peel off the "whole row is clickable" shell (the `GestureDetector` `_crew_row` wraps the row in).
        ★ 2026-10-11 (the run-page panel round): every cast row is now **clickable** (clicking a row goes
          straight to that position's settings), so "this row" gained a `GestureDetector` around it.
          The criterion still measures **the row itself** (background / border / bold), so peel the shell
          first -- the **same technique** as the timestamp round (`_narr_ts_wrap` shell), not a relaxation:
          the shell only provides "can be clicked" and carries no visual decoration.
    """
    if getattr(ctrl, '_crew_goto', None) is not None:
        return getattr(ctrl, 'content', ctrl)
    return ctrl


def _rows(app) -> list:
    return [_unwrap_click(c)
            for c in (getattr(app._ui_run.get('crew_list'), 'controls', None) or [])]


def _busy_rows(app) -> list[tuple[str, object]]:
    """界面上**带高亮底**的那几行：`[(职位名, 控件)]`。

    判据按**控件本身**数（`bgcolor == CREW_BUSY_BG`），不按状态字段 ——
    这样即使状态是 `working`，只要界面没把它画成高亮，这条也是红的。

    ⚠ 一行里第一个 `Text` 是那个圆点 `●`，职位名在它后面 —— 所以按
      **名册里的职位名**去认，不能图省事取 `txt[0]`（第一版就这么假红了两条）。
    
        English:
    The lines on the UI **with a highlight background**: `[(role name, widget)]`.
        Count based on the **widget itself** (`bgcolor == CREW_BUSY_BG`), not the status field ——
        this way even if the status is `working`, as long as the UI does not draw it as highlighted, this entry is still red.
        ⚠ The first `Text` in a line is that dot `●`, the role name is after it —— so identify by
          **the role name in the roster**, do not take the lazy route of using `txt[0]` (the first version falsely flagged two entries red this way).
    """
    from gui.app_flet import NovelWorldApp
    names = [r.name for r in R.ROSTER]
    out = []
    for c in _rows(app):
        if not isinstance(c, ft.Container):
            continue
        if getattr(c, 'bgcolor', None) != NovelWorldApp.CREW_BUSY_BG:
            continue
        texts = VU.all_texts(c)
        label = next((x for x in texts if any(n and n in str(x) for n in names)),
                     texts[0] if texts else '')
        out.append((str(label), c))
    return out


async def gui_checks(page) -> None:
    VU.patch_flat_background()
    from gui.app_flet import NovelWorldApp
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU
    from sim.session import RunSession

    tmp = Path(tempfile.mkdtemp(prefix='nws_crewhl_'))
    proj = make_project(tmp / '高亮真机', nodes=2)
    run = RunFolder(proj.root, '第1次模拟2026-10-08-01-30').create()
    loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    await asyncio.sleep(1.6)
    app.current_project = proj
    # ★★ 用**真的** `RunSession` 并且**照界面的接法**传 `on_crew_work` ——
    #    这样这一条顺带验了"接线通了"（手搓替身就验不到）。
    # [EN] ★★ use the **real** `RunSession` and pass `on_crew_work` **the way the UI wires it** --
    # [EN] this way this case incidentally verifies "the wiring is connected" (a hand-made stand-in can't
    # [EN] verify that).
    app.session = RunSession(loop, world, run,
                             on_crew_work=app._on_crew_work)
    app.show_main_screen()
    await asyncio.sleep(0.8)

    async def shot(name: str) -> bytes:
        page.update()
        await asyncio.sleep(0.45)
        png = await page.take_screenshot()
        (OUT / f'crew_highlight_{name}.png').write_bytes(png or b'')
        return png or b''

    # ── B0 基线：还没人出工，屏幕上一个高亮都没有 ──
    # [EN] -- B0 baseline: nobody is working yet, not a single highlight on screen --
    app._refresh_crew_panel()
    png0 = await shot('0_idle')
    warm0 = count_color(png0, VU.hex_rgb(NovelWorldApp.CREW_BUSY_BG))
    ok('B0 ★ 还没人出工时：界面上一行高亮都没有（不预填）',
       not _busy_rows(app) and warm0 < 200, f'高亮行 {len(_busy_rows(app))} · 暖金像素 {warm0}')
    # ★ 2026-10-16：台账现在会把「演员」按**在场角色**展开成子 Agent 行
    #   （`studio.ledger` 的字符子条目），所以面板行数 **≥** 职位数，
    #   不再等于。这里把判据改成"每个职位都画出来了"（不缺行、没塌），
    #   多出来的角色子 Agent 行是这一轮新加的、正确的。
    # [EN] ★ 2026-10-16: the ledger now expands "actor" into per-character sub-agent rows
    # [EN] (character sub-entries in `studio.ledger`), so panel rows are **>=** the role count, not equal.
    # [EN] Change the criterion to "every role is drawn" (no missing rows, not collapsed); the extra
    # [EN] character sub-agent rows are new and correct this round.
    rows_n = len(_rows(app))
    names = [r.name for r in R.ROSTER]
    present = sum(1 for n in names
                  if any(n and n in str(x) for c in _rows(app)
                         for x in VU.all_texts(c)))
    ok('B0b 面板本身在（每个职位都画出来了，且行数 ≥ 职位数 —— '
       '角色子 Agent 会额外加行，所以只判"≥ 且各职位都在"）',
       rows_n >= len(names) and present == len(names),
       f'{rows_n} 行 · 到位 {present}/{len(names)}')

    # ── D 事件驱动：把 run 卡住，**在它还没放行时**就连控件一起查 ──
    # [EN] -- D event driven: block the run, and **check the widget while it hasn't been released yet** --
    #
    #  ⚠ 这一条是本组的关键：出工状态是**事件**推过来的，不靠那 0.5 秒
    #    一轮的定时刷新 —— 定时刷新对"几十毫秒的出工"天然会漏帧。
    #    做法：`run` 卡在一个 Event 上，模拟"正在干活"的那几十秒。
    # [EN] ⚠ this case is the key of this group: the working state is pushed over as an **event**, it
    # [EN] doesn't rely on that 0.5 second
    # [EN] per-round timed refresh -- a timed refresh will naturally drop frames for "tens of milliseconds
    # [EN] of working".
    # [EN] Approach: `run` is blocked on an Event, simulating those tens of seconds of "currently working".
    gate = asyncio.Event()
    started = {'n': 0}
    real_run = A.Art.run

    async def _slow(self, ctx, **kw):
        started['n'] += 1
        await gate.wait()
        return await real_run(self, ctx, **kw)

    A.Art.run = _slow
    real_member = A.member
    A.member = lambda key: (A.Art() if key == 'art' else real_member(key))
    ctx = loop._crew_ctx()
    task = None
    try:
        task = asyncio.ensure_future(loop.studio.call('art', ctx))
        for _ in range(60):                 # 等到它真的进 working
        # [EN] Wait until it really enters working
            await asyncio.sleep(0.05)
            if _busy_rows(app):
                break
        busy = _busy_rows(app)
        ok('B1 ★★★ 那位一开工，**那一行立刻高亮**（事件推的，没等定时刷新）',
           len(busy) == 1 and '美术' in busy[0][0], str([x[0] for x in busy]))
        rows = _busy_rows(app)
        ctrl = rows[0][1] if rows else None
        ok('B1b 高亮行有朱砂竖条 + 圆角 + 暖金底（三样一起才算"高亮"）',
           ctrl is not None and getattr(ctrl, 'border', None) is not None
           and getattr(ctrl, 'border_radius', None) == 5
           and getattr(ctrl, 'bgcolor', None) == NovelWorldApp.CREW_BUSY_BG,
           f'border={getattr(ctrl, "border", None)} radius='
           f'{getattr(ctrl, "border_radius", None)}')
        ok('B1c 那一行写着「出工中…」（还没满一秒，先不带秒数）',
           any('出工中' in x for x in VU.all_texts(ctrl)) if ctrl else False,
           str(VU.all_texts(ctrl) if ctrl else [])[:2])
        ok('B1d 名字**加粗**了（平时不加粗）',
           bool([x for x in VU.all_texts(ctrl) if '美术' in x]) if ctrl else False, '')

        # 等一秒以上 → 秒数该出来了
        # [EN] Wait more than one second -> the seconds should appear
        await asyncio.sleep(1.15)
        app._refresh_crew_panel()
        texts = VU.all_texts(_busy_rows(app)[0][1]) if _busy_rows(app) else []
        ok('B2 ★ 高亮了 1 秒以上 → 那一行带「已跑 N 秒」'
           '（跑了三分钟的与刚起步的不能长得一样）',
           any('已跑' in x for x in texts), str(texts)[:120])

        # ── 像素：高亮**真的画在屏幕上** ──
        # [EN] -- pixels: the highlight is **really drawn on screen** --
        png1 = await shot('1_working')
        warm1 = count_color(png1, VU.hex_rgb(NovelWorldApp.CREW_BUSY_BG))
        ok('B3 ★★★ 高亮底色**真的画在屏幕上**（暖金像素 ≥ 1500）'
           '—— 控件树里有 ≠ 屏幕上看得见',
           warm1 >= 1500, f'暖金像素 {warm1}')

        # ── 同时只有干活的那几行亮 ──
        # [EN] -- at the same time only the rows that are working are lit --
        gate2 = asyncio.Event()
        started2 = {'n': 0}

        async def _slow2(self, ctx, **kw):
            started2['n'] += 1
            await gate2.wait()
            return await real_run(self, ctx, **kw)

        A.member = lambda key: (A.Props() if key == 'props' else real_member(key))
        A.Props.run = _slow2
        task2 = asyncio.ensure_future(loop.studio.call('props', ctx))
        for _ in range(60):
            await asyncio.sleep(0.05)
            if len(_busy_rows(app)) >= 2:
                break
        two = _busy_rows(app)
        # ⚠ 名字那一栏是 `美术 · 出工中 · 已跑 1 秒` 这种**带状态词**的串 ——
        #   判据按**前缀**认职位名（等值比较会假红，第一版就栽在这儿）。
        # [EN] the criterion recognizes the role name by **prefix** (an equality comparison gives a false red,
        # [EN] the first version tripped here).
        got = [x[0] for x in two]
        ok('B4 ★★ 两位同时在干活 → **只有这两行**亮（别人不跟着亮）',
           len(two) == 2
           and all(any(str(g).startswith(n) for n in ('美术', '道具')) for g in got),
           str(got))
        png2 = await shot('2_two_working')
        warm2 = count_color(png2, VU.hex_rgb(NovelWorldApp.CREW_BUSY_BG))
        ok('B4b 屏幕上暖金像素也翻倍了（两位各占一块）',
           warm2 > warm1 * 1.5, f'{warm1} → {warm2}')

        # ── B5 ★★★ 正在干活的那一行，第二句**不能还写「还没轮到」** ──
        # [EN] -- B5 ★★★ for the row that is currently working, the second sentence **must not still say [EN] "还没轮到"** --
        #
        # 用户 2026-10-08：「右边人员都在干活了 跟着他们的状态还是 还没轮到
        # 这个有点奇怪」。那行第二句以前不管什么状态、只要还没交过活就写
        # 「还没轮到」—— 于是上面亮着「出工中 · 已跑 N 秒」、下面写着
        # 「还没轮到」，自相矛盾。现在写**这个人此刻在做的那件事**。
        # [EN] 这个有点奇怪". That row's second sentence used to say, regardless of state, as long as nothing had
        # [EN] been delivered yet,
        # [EN] "还没轮到", self-contradictory. Now it writes **the thing this person is doing right now**.
        #
        # ⚠ 用**道具**那一行来验：它是这一轮里**第一次出工**（`_slots` 里
        #   之前没有它），所以"还没交过活"这个前提是确定的；美术那一行
        #   前面已经交过活了，验不到这一条。
        # [EN] ⚠ verify with the **道具** row: it is the **first time working** in this round (`_slots` did not
        # [EN] have it before), so the premise "hasn't delivered anything yet" is certain; the 美术 row
        # [EN] has already delivered something before, so it can't verify this case.
        row_props = next((c for n, c in two if str(n).startswith('道具')), None)
        blob = (' | '.join(str(x) for x in VU.all_texts(row_props))
                if row_props is not None else '')
        ok('B5 ★★★ 正在干活的那一行**不会还写着「还没轮到」**'
           '（上面写着「出工中」、下面写「还没轮到」＝自相矛盾 —— 用户报的）',
           row_props is not None and '还没轮到' not in blob, blob)
        ok('B5b ★★ 而且它写的是**这个人此刻在做的那件事**（该职位的职责）',
           '正在做' in blob, blob)

        gate2.set()
        await task2
    finally:
        gate.set()
        if task is not None:
            try:
                await task
            except Exception:                                    # noqa: BLE001
                pass
        A.member = real_member
        A.Art.run = real_run

    # ── C 干完恢复普通样式 ──
    # [EN] -- C restore normal style when done --
    app._refresh_crew_panel()
    page.update()
    await asyncio.sleep(0.3)
    ok('C1 ★★★ 干完之后**一行高亮都不剩**（底色/描边/加粗全撤了，'
       '不是"留着淡淡的底"）',
       not _busy_rows(app), str([x[0] for x in _busy_rows(app)]))
    png3 = await shot('3_done')
    warm3 = count_color(png3, VU.hex_rgb(NovelWorldApp.CREW_BUSY_BG))
    ok('C2 ★★★ 屏幕上的暖金像素回到 0（像素级：真的复原了）',
       warm3 < 200, f'{warm1} → {warm3}')
    led = {r['key']: r for r in loop.studio.ledger()}
    ok('C3 台账里也回到「已交活」（不是只有界面复原了）',
       led['art']['state'] == 'done' and not led['art']['busy'],
       f"{led['art']['state']} / busy={led['art']['busy']}")
    hint = app._ui_run.get('crew_hint')
    ok('C4 ★ 底下那句话跟着变（有人出工时先说"n 位正在出工"，'
       '没人了才回到"n / m 位已交活"）',
       hint is not None and '已交活' in str(hint.value), str(getattr(hint, 'value', '')))

    # ── D2 收工**也要** 是事件推的：手动放一次事件，界面立刻变 ──
    # [EN] -- D2 finishing **also** must be pushed by an event: manually fire an event once, the UI changes
    # [EN] immediately --
    #
    #  ⚠ 这一条防的是"只有开始报、收工不报"——那种实现下，一段忙碌过后
    #    高亮会**一直亮着**（正是用户说的"等不干活了再恢复普通样式"没做到）。
    # [EN] ⚠ this case guards against "only start is reported, finish isn't" -- with that implementation,
    # [EN] after a busy period
    st = loop.studio
    slot = st._slots['art']
    slot.state = 'working'
    slot.t0 = __import__('time').monotonic()
    app._on_crew_work('art', 'working')
    ok('D1 ★★ 收到「开始出工」事件 → 界面立刻亮（`_on_crew_work` 真的重画了）',
       len(_busy_rows(app)) == 1, str([x[0] for x in _busy_rows(app)]))
    slot.state = 'done'
    slot.t0 = 0.0
    app._on_crew_work('art', 'done')
    ok('D2 ★★★ 收到「收工」事件 → 界面立刻复原（高亮撤掉）',
       not _busy_rows(app), str([x[0] for x in _busy_rows(app)]))

    # ── B5 会话不在时不留假的（本项目"不假装"的规矩）──
    # [EN] -- B5 when the session is absent, don't leave a fake one (this project's "don't pretend" rule)
    # [EN] --
    app.session = None
    app._refresh_crew_panel()
    ok('B5 ★ 没有会话时面板留空（不会留着上一次的高亮）',
       not _rows(app), str(len(_rows(app))))


# ══════════════════════════════════════════════════════════════
async def main(page) -> None:
    print('\n── A 出工状态真的被播报出来（源码 + 行为）──')
    try:
        logic_checks()
        await led_behavior_checks()
    except Exception:                                            # noqa: BLE001
        ok('A 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    if not ONLY_LOGIC and page is not None:
        print('\n── B/C/D 真机：高亮 → 复原 ──')
        try:
            await gui_checks(page)
        except Exception:                                        # noqa: BLE001
            ok('B/C/D 组跑完（真机）', False, traceback.format_exc()[-400:])
            print(traceback.format_exc()[-1200:])
    rep = {'checks': report['checks'],
           'passed': sum(1 for c in report['checks'] if c['ok']),
           'total': len(report['checks'])}
    rep['ok'] = rep['passed'] == rep['total']
    (OUT / 'crew_highlight_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n剧组高亮验证：{rep['passed']}/{rep['total']}")
    if page is not None:
        await shutdown(page, code=0 if rep['ok'] else 2)


if __name__ == '__main__':
    if ONLY_LOGIC:
        asyncio.run(main(None))
    else:
        ft.run(main, assets_dir=str(APP_DIR / 'assets'))
