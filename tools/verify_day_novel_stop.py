# -*- coding: utf-8 -*-
"""验证：**"整理当天这一章"尊重停止 + 状态条看得见进度**（2026-10-24）。

用户报的现象
------------
    「你看下**小说作家2800多秒还没结束**是什么原因」
    「我希望左下角的状态……显示运行中 等下一次行动 xxxx 做什么 时间s」

日志实测（`nws_望江楼模拟项目_2026_10_24_17_38_26.log`）
------------------------------------------------------
  · 21:50:56 起跑 `novelize`，22:40:07 结束 —— **2950.9 秒**，而且日志里标的是
    **（失败）**（`Studio.stage()` 只在**抛异常**时标失败）。
  · 22:22:44 用户点了停止（有 `UI 操作: 停止推演`，落盘也做了），
    **可整理稿又一段一段写了 17 分钟**，直到 22:40:07 进程收尾才被取消。
  · 那 49 分钟里干了什么：材料 4.7 万字切 **18 段**，每段之后跑一整套
    Reflexion（8 步 / 最多 5 轮）；**93 次模型调用**（69 次 crew_day_novel
    + 24 次 prose_flow_fix）。
  · 22:32→22:39 有 **8 次报的是同一句话、同一个数字**：
    `细节复读「墙那张」3 次（上限 2）；细节复读「塞进」3 次（上限 2）`
    —— `patience`（按**加权总分**判"这一轮有没有进步"）一直没触发，
    因为别的类还在降，总分每轮都在降一点点。

判据分组（一条判据守一道闸）
--------------------------
  A **尊重停止**：每段开始前问一次；停了就**不再写下一段**
  B **停下也不丢**：已经写好的段要留住，并且**说清只到第几段**，
     而且不能标成失败（标失败 ⇒ 一个字都不落盘 ⇒ 已花的钱全扔）
  C **一段没写就停**要说清是"还没开始就停了"，不能写成"整理出来是空的"
  D **状态条看得见进度**：段进度进 `DOING` 栈，退出后回落到外层（栈不能漏）
  E **修不动的类不再反复烧**：某类连着两轮一个数都没动 ⇒ 下一轮跳过；
     但**只给它一次机会**（一轮没动不算，模型有抖动）

跑法：.venv\\Scripts\\python.exe tools/verify_day_novel_stop.py
产出：assets/screenshots/day_novel_stop_report.json

English:
Verify that **"organize today's chapter" respects stop + the status bar shows progress**
(2026-10-24).
What the user reported: "why has the novelist been running 2800+ seconds without finishing", and
"I want the bottom-left status to show running / waiting for next action / doing X / N seconds".
Measured in the log: `novelize` started 21:50:56 and ended 22:40:07 -- **2950.9 s**, flagged
**(failed)** (`Studio.stage()` marks failure only on an **exception**). At 22:22:44 the user clicked
stop (`UI: stop simulation`, flush ran), yet the organized draft kept writing chunk after chunk for
another 17 minutes. What those 49 minutes did: 47k characters split into **18 chunks**, each followed
by a full Reflexion pass (8 steps / up to 5 rounds); **93 model calls**. From 22:32 to 22:39 the same
sentence with the same numbers was reported **eight times**, while `patience` (which judges progress on
the **weighted total**) never fired because other classes kept dropping.
Groups: A respects stop / B a stopped draft is still delivered and says where it ends / C "stopped
before starting" is not "came out empty" / D the status bar shows chunk progress and the stack unwinds
/ E a class that has not moved for two rounds is skipped -- but it gets one chance first.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from config import CFG                                       # noqa: E402
from crew.agents import Novelist, SetCtx                     # noqa: E402
from crew import doing as DOING                              # noqa: E402
from crew import reflexion as RX                             # noqa: E402
from crew import verdict as V                                # noqa: E402

OUT = APP / 'assets' / 'screenshots'
REPORT = OUT / 'day_novel_stop_report.json'
_rows: list[dict] = []


def ok(name: str, cond, detail='') -> bool:
    _rows.append({'判据': name, '通过': bool(cond), '实测': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''))
    return bool(cond)


# ── 夹具 ────────────────────────────────────────────────────────
class _Loop:
    def __init__(self, stopping: bool = False):
        self.stopping = stopping


class _World:
    style_card: dict = {}
    extras_engaged: list = []

    def on_stage_names(self) -> list:
        return ['甲', '乙']

    def world_brief(self, n: int = 500) -> str:
        return '世界观简述'


def _ctx(stopping: bool = False) -> SetCtx:
    ctx = SetCtx(world=_World(), db=None, day=1)
    ctx.loop = _Loop(stopping)
    return ctx


def _body(lines: int = 60) -> str:
    """一段足够长、能切成好几块的"当天材料"（按行，与真实材料同形）。"""
    return '\n'.join(f'第 {i} 行：有人起身，走到柜边，说了句「知道了」。'
                     for i in range(lines))


class _Stub(Novelist):
    """把 `_transcribe_once` 打桩：不调模型，只记"被叫了几次"。"""

    def __init__(self, *, stop_after: int = 0):
        self.calls: list[str] = []
        self.seen_doing: list[str] = []
        self._stop_after = stop_after       # 叫到第 N 次之后把 stopping 置真

    async def _transcribe_once(self, ctx, body, *, scope='', link='',
                               craft='', cot_block='', **kw):
        # ⚠ `**kw`：2026-10-26 起调用点会多传 `unit_block` / `target`
        #   （按情节单元写，见 `crew/unit_plan.py`）。替身**必须**跟着收，
        #   否则 TypeError → 这组全红，而红的原因是"替身过期"，与停止无关。
        # [EN] `**kw`: since 2026-10-26 the call site also passes `unit_block` / `target`
        # [EN] (write by plot unit). The double **must** accept them, or a TypeError turns the
        # [EN] whole group red for a reason that has nothing to do with stopping.
        self.calls.append(scope[:16])
        self.seen_doing.append(DOING.snapshot().get('label') or '')
        if self._stop_after and len(self.calls) >= self._stop_after:
            ctx.loop.stopping = True
        return '这一段写好了。' * 12


def _run(stub: _Stub, ctx: SetCtx, body: str):
    return asyncio.run(stub._transcribe(ctx, body))


# ══════════════════════════════════════════════════════════════
#  A —— 尊重停止
# ══════════════════════════════════════════════════════════════
def _stop_asked_inside_pass_loop() -> tuple[bool, str]:
    """AST：**写作次循环体内**真的调了 `_stop_asked()`。

    ⚠ 2026-10-26 改口径的**唯一理由**：那个循环的变量从 `chunk` 改名成 `job`
      （整理改成"按情节单元写"，循环项不再是字数块）。原来靠字符串
      `'for idx, chunk in enumerate(chunks)'` 认它 —— 改个变量名判据就红，
      而"问不问停止"这件事一个字都没变。
      ⇒ 换成 AST：找 `_transcribe` 里**任何一个** `for` 循环，只要它的循环体里
      出现 `_stop_asked()`，就算问到。这比字符串更严（它不认名字，只认结构）。

    [EN] AST check: inside the writing-pass loop, `_stop_asked()` is really called. The only
    [EN] reason for changing the anchor (2026-10-26): the loop variable was renamed `chunk` ->
    [EN] `job` (organizing is now per plot unit). The old string anchor went red on a rename while
    [EN] "does it ask about stop" had not changed at all. This version does not trust names, only
    [EN] structure -- stricter than the string it replaces.
    """
    import ast
    src = (APP / 'crew' / 'agents.py').read_text(encoding='utf-8')
    try:
        tree = ast.parse(src)
    except SyntaxError as e:                                  # noqa: BLE001
        return False, f'语法错误：{e}'
    for n in ast.walk(tree):
        if not (isinstance(n, ast.AsyncFunctionDef) and n.name == '_transcribe'):
            continue
        for loop in ast.walk(n):
            if isinstance(loop, (ast.For, ast.AsyncFor)):
                for inner in ast.walk(loop):
                    if (isinstance(inner, ast.Call)
                            and isinstance(inner.func, ast.Name)
                            and inner.func.id == '_stop_asked'):
                        return True, ''
    return False, '没找到"循环体里问停止"的结构'


def a_stop() -> None:
    print('\n【A】尊重停止')
    CFG.set('CREW_DAY_NOVEL_CHUNK', '300')
    src = (APP / 'crew' / 'agents.py').read_text(encoding='utf-8')
    _asked, _why = _stop_asked_inside_pass_loop()
    ok('A1 ★★★ 段循环里**真的问了"该不该停"**（不再是闷头写完 18 段）'
       '—— 用户 2026-10-24：点了停止又跑了 17 分钟',
       _asked, _why)
    ok('A2 ★★ 问的是**主循环那个 `stopping`**（不是另造一个标志）'
       '—— 与写样章那条路同一份口径',
       "getattr(lp, 'stopping', False)" in src, '')

    # ① 一上来就停 ⇒ 一次都不调模型
    st = _Stub()
    note = _run(st, _ctx(stopping=True), _body())
    ok('A3 ★★★ 已经点了停止 ⇒ **一段都不写**（一次模型调用都没有）',
       len(st.calls) == 0, f'调用 {len(st.calls)} 次')

    # ② 写到第 2 段前停 ⇒ 只写 1 段
    st2 = _Stub(stop_after=1)
    note2 = _run(st2, _ctx(), _body())
    ok('A4 ★★★ 中途点了停止 ⇒ **不再写下一段**（第 2 段之后一次都没调）',
       len(st2.calls) == 1, f'调用 {len(st2.calls)} 次')


# ══════════════════════════════════════════════════════════════
#  B —— 停下也不丢
# ══════════════════════════════════════════════════════════════
def b_keep() -> None:
    print('\n【B】停下也不丢')
    CFG.set('CREW_DAY_NOVEL_CHUNK', '300')
    st = _Stub(stop_after=1)
    note = _run(st, _ctx(), _body())
    body = str(note.body or '')
    ok('B1 ★★★ 停下时**已经写好的那一段留下来**（不能因为点了停止就扔掉 —— '
       '钱已经花掉了）',
       '这一段写好了' in body, f'{len(body)} 字')
    ok('B2 ★★★ 而且**说清只到第几段**（用户拿到稿子要知道后面缺）',
       '点了停止' in body and '段' in body, body[-46:].replace('\n', ' '))
    ok('B3 ★★★ **不标失败**（标失败 ⇒ `_day_novel` 一个字都不落盘 ⇒ 已花的钱全扔）',
       bool(note.ok), f'ok={note.ok} why={note.why!r}')


# ══════════════════════════════════════════════════════════════
#  C —— 一段没写就停，理由要说对
# ══════════════════════════════════════════════════════════════
def c_reason() -> None:
    print('\n【C】理由要说对')
    CFG.set('CREW_DAY_NOVEL_CHUNK', '300')
    note = _run(_Stub(), _ctx(stopping=True), _body())
    why = str(note.why or '')
    ok('C1 ★★★ 一段没写就停 ⇒ 理由说「还没开始就点了停止」'
       '（"整理出来是空的"是另一件事：那句说的是模型没产出）',
       '停止' in why, why)


# ══════════════════════════════════════════════════════════════
#  D —— 状态条看得见进度
# ══════════════════════════════════════════════════════════════
def d_doing() -> None:
    print('\n【D】状态条看得见进度')
    CFG.set('CREW_DAY_NOVEL_CHUNK', '300')
    DOING.reset()
    st = _Stub()
    outer = DOING.push('整理当天这一章')
    try:
        _run(st, _ctx(), _body())
    finally:
        pass
    ok('D1 ★★★ 每一段期间 `DOING` 栈顶都写着**第几段/共几段**'
       '—— 49 分钟只挂一个死标签，正是"2800 多秒还没结束"的观感来源',
       bool(st.seen_doing) and all('整理第' in x for x in st.seen_doing),
       f'{st.seen_doing[:3]}…')
    ok('D2 ★★★ 段结束后**回落到外层**（不是把外层的标签也弹掉）'
       '—— 阶段是嵌套的，`pop` 必须按令牌',
       DOING.snapshot().get('label') == '整理当天这一章',
       f'栈顶={DOING.snapshot().get("label")!r}')
    DOING.pop(outer)
    ok('D3 ★★ 全部结束后**栈是空的**（不许留一个永不退的标签）',
       DOING.snapshot().get('label') == '',
       f'栈顶={DOING.snapshot().get("label")!r}')


# ══════════════════════════════════════════════════════════════
#  E —— 修不动的类不再反复烧
# ══════════════════════════════════════════════════════════════
def e_stalled() -> None:
    print('\n【E】修不动的类不再反复烧')
    s = V.Score(counts={'细节复读': 3, '段落拥挤': 2})
    ok('E1 ★★★ 某类**已经归零** ⇒ 跳过（老规则，别弄丢）',
       RX._should_skip('细节复读', V.Score(counts={'细节复读': 0}), set()) != '', '')
    ok('E2 ★★★ 某类**被自己改多了** ⇒ 跳过（老规则，别弄丢）',
       RX._should_skip('细节复读', s, {'细节复读'}) != '', '')
    ok('E3 ★★★ 某类**连着两轮一个数都没动** ⇒ 跳过'
       '—— 日志里那两处一字不差地报了 8 次，5 轮全烧在上面',
       RX._should_skip('细节复读', s, set(), {'细节复读'}) != '', '')
    ok('E4 ★ ★ `元叙述` **永不跳过**（它是确定性剥离，不会写进新东西）',
       RX._should_skip('元叙述', s, {'元叙述'}, {'元叙述'}) == '', '')

    # ⑤ 行为级：修不动的类只跑 2 轮（给一次机会），能修的照旧跑满
    calls = {'A': 0, 'B': 0}

    async def step_a(t):
        calls['A'] += 1
        return t + ' a'

    async def step_b(t):
        calls['B'] += 1
        return t + ' b'

    orig = V.Score.of

    def fake_of(_t):
        return V.Score(counts={'A类': 3, 'B类': max(0, 4 - calls['B'])})

    V.Score.of = staticmethod(fake_of)
    try:
        RX.reflect_result = None
        asyncio.run(RX.reflect('base', [(step_a, 'A类'), (step_b, 'B类')],
                               trials=5, patience=5))
    finally:
        V.Score.of = orig
    ok('E5 ★★★ 行为级：修不动的类**第 2 轮之后就不再调模型**，'
       '能修的那类照旧跑（这是省钱的那一半）',
       calls['A'] == 2 and calls['B'] >= 3, f'A={calls["A"]} B={calls["B"]}')
    ok('E6 ★★★ 但**先给它一次机会**（一轮没动不算 —— 模型有抖动，'
       '写成"与上一轮相同就跳"会第 1 轮就放弃）',
       calls['A'] >= 2, f'A={calls["A"]}')


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print('═' * 62)
    print('  整理稿：尊重停止 + 看得见进度（2026-10-24）')
    print('═' * 62)
    for fn in (a_stop, b_keep, c_reason, d_doing, e_stalled):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f'{fn.__name__} 整组没跑完：{e!r}', False, '')

    bad = [r for r in _rows if not r['通过']]
    print('\n' + '─' * 62)
    print(f'  整理稿停止 + 进度验证：{len(_rows) - len(bad)}/{len(_rows)}'
          + ('   ← 有失败' if bad else ''))
    for r in bad:
        print(f'    ! {r["判据"]}  [{r["实测"]}]')
    print('─' * 62)
    REPORT.write_text(json.dumps(_rows, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
