# -*- coding: utf-8 -*-
"""真机/逻辑验证：**剧组面板常驻岗（导演 / 演员 / 群众演员）开拍后显示「在岗」**。

用户 2026-10-15 的原话：
    「对话界面中 已经进行了很多轮了 导演 演员和群众演员都已经登场了
      但是右边剧组成员列表里的导演 演员 群众演员状态都是还没登场 开工
      这个是不对的」

根因（见 `crew/studio.py::mark_onduty` / `report_onduty` 注释）：
    导演/演员/群众演员继承 `OnDuty`，每拍直接 `on_tick()`，**不经 `Studio.call`**，
    所以整天的出工在台账里**没有 `working`/`done` 的痕迹** —— 只有收工时
    `report_onduty` 才补 `done`。推演进行中（没到收工），界面那三行永远停在
    初始的 `idle`（待命），与"他们其实一整天都在干活"自相矛盾 —— 正是
    `report_onduty` 注释自己承认的"界面说假话"。

修复：开拍即由 `Studio.mark_onduty()` 把三者标成新状态 `onduty`（在岗）；
    收工仍由 `report_onduty` 走到 `done`。界面 `_refresh_crew_panel` 照实显示：
    `onduty` 行写「在岗 · 正在做：…」、不再写「还没轮到」，且**不高亮**
    （它不是"正在出工"那种有 LLM 调用的忙，只是常驻在场）。

判据（行为级为主，源码/接线为辅）：
  A **`mark_onduty` 真的把三者标成 `onduty`**（行为）
      · A1 `Studio` 真有 `mark_onduty` 这个方法（不是名字写错）；
      · A2 调一次之后，导演/演员/群众演员在 `ledger()` 里 `state=='onduty'`
        且 `busy==False`（在岗 ≠ 高亮），其余角色不受影响；
      · A3 标在岗时会通过 `on_work` 播报 `onduty` 事件（界面据此刷那三行）；
      · A4 `_CREW_STATE_STYLE` 含 `onduty`（界面知道用哪种样式画它）。
  B **`_refresh_crew_panel` 照实显示（行为，不靠显示）**
      · B1 每个 `onduty` 行第二句含「在岗」且**不含**「还没轮到」；
      · B2 每个 `onduty` 行**不高亮**（没有暖金底 —— 在岗不是"出工中"）；
      · B3 真·idle 角色仍显示「还没轮到」、`off` 角色仍显示「这一轮没启用」
        （确认我没把 idle/off 分支改坏）；
  C **开拍即标在岗（接线，AST）**
      · C1 `RunLoop` 每个调 `await self._open_day()` 的方法里，都**在其后**
        调了 `self.studio.mark_onduty()`（跨天分支 + 第一天分支两处都接上）。

跑法：
    .venv\\Scripts\\python.exe tools/verify_crew_onduty.py
产出：
    assets/screenshots/crew_onduty_report.json

English:
Real-machine / logic verification: **the crew panel's on-duty residents (director / actor / extra)
show "在岗 (onduty)" after shooting opens**.
User 2026-10-15 exact words: after many rounds, director/actor/extra have all appeared, but the
right-side crew list still shows them as "not yet started / not on duty" -- that's wrong.
Root cause: those three inherit `OnDuty` and call `on_tick()` directly every beat, **not through
`Studio.call`**, so their all-day work leaves no `working`/`done` trace in the ledger until wrap-up.
Fix: at shoot-open `Studio.mark_onduty()` marks them `onduty`; `report_onduty` at wrap walks them to
`done`. The panel honestly shows "在岗 · 正在做：…" and is **not highlighted** (onduty ≠ working).
Criteria (behavior-first, source/wiring为辅):
  A mark_onduty really marks the three onduty (behavior)
  B _refresh_crew_panel shows it honestly (behavior, no display)
  C shoot-open wires mark_onduty (AST)
How to run: .venv\\Scripts\\python.exe tools/verify_crew_onduty.py
Output: assets/screenshots/crew_onduty_report.json
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
from util.flet_shutdown import shutdown                         # noqa: E402
import verify_ui_common as VU                                  # noqa: E402

from config import CFG                                         # noqa: E402
# ⚠ 起界面的脚本第一条就是这个重定向（见 `verify_crew_highlight.py` 头部说明）：
#   `CFG.save()` 会把下面的测试值写进用户的 `.env`。这里虽然没有 `app.main()`，
#   但保险起见仍然重定向。
# [EN] ⚠ First line of any UI-starting script is this redirect (see header of verify_crew_highlight.py):
# [EN] CFG.save() would write the test values below into the user's `.env`. We don't call app.main() here,
# [EN] but redirect anyway to be safe.
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')          # 零网络、零成本、可复现

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from crew import studio as ST                                   # noqa: E402
from gui.app_flet import NovelWorldApp                          # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _texts(ctl, out=None):
    """递归收一行控件里所有 `Text.value`（剥掉"整行可点"外壳也能用）。
        English:
    Recursively collect all `Text.value` in one row of controls (works even after
    peeling the clickable shell).
    """
    if out is None:
        out = []
    if ctl is None:
        return out
    if isinstance(ctl, ft.Text) and ctl.value:
        out.append(str(ctl.value))
    if isinstance(ctl, ft.GestureDetector):
        _texts(ctl.content, out)
        return out
    for attr in ('controls', 'content'):
        v = getattr(ctl, attr, None)
        if isinstance(v, list):
            for c in v:
                _texts(c, out)
        elif isinstance(v, ft.Control):
            _texts(v, out)
    return out


# ══════════════════════════════════════════════════════════════
#  A —— mark_onduty 真的把三者标成 onduty
# [EN] A -- mark_onduty really marks the three onduty
# ══════════════════════════════════════════════════════════════
def logic_checks() -> None:
    # ── A1 方法真存在 ──
    ok('A1 ★★★ 制片厂有 `mark_onduty()` 这个方法（不是名字拼错 / 没接上）',
       callable(getattr(ST.Studio, 'mark_onduty', None)), '')

    # ── A2 行为：调一次后三者 state==onduty 且 busy==False ──
    st = ST.Studio(world=None, db=None)
    present = [k for k in ('director', 'actor', 'extra') if k in st._slots]
    ok('A2a ★ 名册里确有导演/演员/群众演员三位常驻岗',
       set(present) == {'director', 'actor', 'extra'}, str(present))
    before = {r['key']: r['state'] for r in st.ledger()}
    st.mark_onduty()
    led = {r['key']: r for r in st.ledger()}
    for k in present:
        ok(f'A2 ★★★ 开拍后 {k} 标为 `onduty` 且 `busy=False`（在岗 ≠ 高亮）',
           led[k]['state'] == 'onduty' and not led[k]['busy'],
           f"state={led[k]['state']} busy={led[k]['busy']}")
    # 其它角色不受影响（仍是它们自己的状态，不被强行改成 onduty）
    others = [k for k in led if k not in present]
    untouched = all(led[k]['state'] == before.get(k, led[k]['state']) for k in others)
    ok('A2b 其它角色状态不受牵连（mark_onduty 只动那三位常驻岗）',
       untouched, f'others={[ (k, led[k]["state"]) for k in others[:4] ]}')

    # ── A3 标在岗会播报 onduty 事件（界面据此刷那三行）──
    seen: list[tuple[str, str]] = []
    st2 = ST.Studio(world=None, db=None,
                    on_work=lambda k, s: seen.append((str(k), str(s))))
    st2.mark_onduty()
    got = sorted(seen)
    exp = sorted([('director', 'onduty'), ('actor', 'onduty'), ('extra', 'onduty')])
    ok('A3 ★★★ 标在岗时通过 `on_work` 播报 `onduty` 事件'
       '（界面据此立刻重画那三行）',
       got == exp, str(got))

    # ── A4 界面知道怎么画 onduty ──
    ok("A4 ★★ `_CREW_STATE_STYLE` 含 `onduty`"
       '（界面按状态挑样式，缺了这个键就会回退成灰点）',
       'onduty' in NovelWorldApp._CREW_STATE_STYLE,
       str(NovelWorldApp._CREW_STATE_STYLE.get('onduty')))


# ══════════════════════════════════════════════════════════════
#  B —— _refresh_crew_panel 照实显示（行为，不靠显示）
# [EN] B -- _refresh_crew_panel shows it honestly (behavior, no display)
# ══════════════════════════════════════════════════════════════
def panel_checks() -> None:
    st = ST.Studio(world=None, db=None)
    st.mark_onduty()

    # 用**真的** `_refresh_crew_panel` + **真的** `ledger()`，只把会话/列桩掉
    # （不接 page、不截图）—— 量的是"那一行到底写了什么字、有没有高亮底"。
    # [EN] Use the **real** `_refresh_crew_panel` + **real** `ledger()`, stub only the
    # session/column (no page, no screenshot) -- what we measure is "what text that row
    # actually carries, and whether it has a highlight background".
    class _Loop:
        def __init__(self, s):
            self.studio = s

    class _Ses:
        def __init__(self, s):
            self.loop = _Loop(s)

    app = object.__new__(NovelWorldApp)
    app._ui_run = {'crew_list': ft.Column(), 'crew_hint': ft.Text()}
    app.session = _Ses(st)
    app._refresh_crew_panel()

    rows = st.ledger()
    controls = app._ui_run['crew_list'].controls
    ok('B0 ★ 面板画出的行数与台账一致（不是整个面板塌了）',
       len(controls) == len(rows), f'{len(controls)} vs {len(rows)}')
    if len(controls) != len(rows):
        return

    for r, ctrl in zip(rows, controls):
        blob = ' | '.join(_texts(ctrl))
        stt = r['state']
        if stt == 'onduty':
            ok(f'B1 ★★★ {r["key"]} 行显示「在岗」且**不再写「还没轮到」'
               '（用户报的那条"都登场了还显示没开工"）',
               '在岗' in blob and '还没轮到' not in blob, blob)
            # 在岗 ≠ 出工中：那一行不应有暖金高亮底
            # [EN] onduty ≠ working: that row must not carry the warm-gold highlight bg
            inner = ctrl.content if getattr(ctrl, '_crew_goto', None) is not None else ctrl
            hl = isinstance(inner, ft.Container) and (
                getattr(inner, 'bgcolor', None) == NovelWorldApp.CREW_BUSY_BG)
            ok(f'B2 ★★★ {r["key"]} 行**不高亮**（没有暖金底 —— 在岗不是"出工中"）',
               not hl, f'type={type(inner).__name__} hl={hl}')
        elif stt == 'idle':
            ok(f'B3 {r["key"]} 行仍显示「还没轮到」'
               '（确认 idle 分支没被我改坏）',
               '还没轮到' in blob, blob)
        elif stt == 'off':
            ok(f'B3b {r["key"]} 行仍显示「这一轮没启用」'
               '（确认 off 分支没被我改坏）',
               '这一轮没启用' in blob, blob)

    # 底下那句提示：有人在岗、且此刻没人在"出工中"时，说"n 位在岗"
    # [EN] the hint at the bottom: when someone is onduty and nobody is "working" right now,
    # say "n 位在岗"
    hint = app._ui_run.get('crew_hint')
    onduty_n = sum(1 for r in rows if r['state'] == 'onduty')
    busy_n = sum(1 for r in rows if r['busy'])
    hv = str(getattr(hint, 'value', ''))
    ok('B4 ★ 有人在岗、此刻没人出工中 → 提示说"n 位在岗"'
       '（不再说"点起笔开拍后…"那种还没开拍的话）',
       (busy_n == 0 and onduty_n > 0 and '在岗' in hv) or (onduty_n == 0),
       f'busy_n={busy_n} onduty_n={onduty_n} hint={hv}')


# ══════════════════════════════════════════════════════════════
#  C —— 「演员」按在场角色展开成子 Agent（2026-10-16）
# [EN] C -- "actor" expands into per-character sub-agents (2026-10-16)
# ══════════════════════════════════════════════════════════════
class _FakeWorld:
    """最小可替身的「世界」：只给台账要的两样东西
        （在场名单 + 各人最近盘算），不接真模型。
        English:
    Minimal stand-in "world": only the two things the ledger needs
    (on-stage list + each one's recent deliberation), no real model.
    """
    def on_stage_names(self):
        return ['林黛玉', '贾宝玉']

    actor_think = {'林黛玉': '该不该把帕子收起来',
                   '贾宝玉': '盯着那本书出神'}
    # ★ 决策完成时间戳（2026-10-16 高亮用）：测试里手动写，默认空。
    # [EN] decision-completion timestamps (2026-10-16 highlight): written in tests, empty by default.
    actor_think_at = {}


def char_checks() -> None:
    st = ST.Studio(world=_FakeWorld(), db=None)
    st.mark_onduty()
    led = {r['key']: r for r in st.ledger()}

    # ── C1 台账真的挂了"演员::{角色}"子条目，且是在岗 ──
    # [EN] C1 ledger really hangs "actor::{character}" sub-entries, onduty
    for nm in ('林黛玉', '贾宝玉'):
        key = f'actor::{nm}'
        ok(f'C1 ★★★ 台账挂了子 Agent「演员·{nm}」（key={key}）',
           key in led, f'keys={[k for k in led if "::" in k]}')
        if key in led:
            r = led[key]
            ok(f'C1b 「演员·{nm}」是 `onduty` 且 `busy=False`（在岗 ≠ 高亮）',
               r['state'] == 'onduty' and not r['busy'],
               f"state={r['state']} busy={r['busy']}")
            ok(f'C1c 「演员·{nm}」带 parent=actor / is_sub=True'
               '（面板据此缩进、且不算进角色级"在岗"计数）',
               r.get('parent') == 'actor' and r.get('is_sub') is True,
               f"parent={r.get('parent')} is_sub={r.get('is_sub')}")

    # ── C2 子条目按"模拟自己记的盘算"显示活动（不是界面编的）──
    # [EN] C2 sub-entries show activity from what the sim recorded (not invented by UI)
    ok('C2 ★★★ 子 Agent 的活动取自 `world.actor_think`'
       '（「演员·林黛玉」的 duty 是它最近的盘算）',
       led['actor::林黛玉']['duty'] == '该不该把帕子收起来',
       led['actor::林黛玉']['duty'])
    ok('C2b 「演员·贾宝玉」同理取自它自己的盘算',
       led['actor::贾宝玉']['duty'] == '盯着那本书出神',
       led['actor::贾宝玉']['duty'])

    # ── C3 面板：子行显示「在岗」、不写「还没轮到」 ──
    #   ★ 2026-10-17：这几行**搬到「在场人物」那一栏了**（用户点名要的搬家），
    #     所以这里看的是 `char_list`，不是 `crew_list`。
    #     「在场人物」自己那份判据在 `verify_run_side_panels.py`；
    #     这里只守"搬过去之后说法没变" —— 状态、在做的事一律照旧。
    # [EN] C3 panel: sub-row shows "在岗", not "还没轮到"
    # [EN]   ★ 2026-10-17: these rows **moved to the "On-stage Characters" column** (the move the user
    # [EN]     asked for by name), so we look at `char_list` here, not `crew_list`.
    # [EN]     "On-stage Characters" has its own criteria in `verify_run_side_panels.py`;
    # [EN]     here we only guard "the wording didn't change after the move" -- status and what it's
    # [EN]     doing are all as before.
    class _Loop:
        def __init__(self, s):
            self.studio = s

    class _Ses:
        def __init__(self, s):
            self.loop = _Loop(s)

    app = object.__new__(NovelWorldApp)
    app._ui_run = {'crew_list': ft.Column(), 'crew_hint': ft.Text(),
                   'char_list': ft.Column(), 'char_hint': ft.Text()}
    app.session = _Ses(st)
    app._refresh_crew_panel()
    app._refresh_char_panel()
    crew_controls = app._ui_run['crew_list'].controls
    controls = app._ui_run['char_list'].controls
    rows = st.ledger()
    subs = [r for r in rows if r.get('is_sub')]
    non_subs = [r for r in rows if not r.get('is_sub')]
    crew_keys = {r['key'] for r, _ in zip(non_subs, crew_controls)}
    ok('C3a ★★★ 「在场人物」那一栏的行数 = 台账里 `is_sub` 的行数'
       '（一个在场角色一行，不多不少）',
       len(controls) == len(subs), f'{len(controls)} vs {len(subs)}')
    by_key = {r['key']: (r, ctrl) for r, ctrl in zip(subs, controls)}

    for nm in ('林黛玉', '贾宝玉'):
        key = f'actor::{nm}'
        r, ctrl = by_key.get(key, (None, None))
        blob = ' | '.join(_texts(ctrl)) if ctrl is not None else ''
        ok(f'C3 ★★★ 面板「演员·{nm}」显示「在岗」且**不写「还没轮到」',
           '在岗' in blob and '还没轮到' not in blob, blob)
        # ★ 搬走了 ⇒ 「剧组」那一栏**不能再有它**。
        # [EN] ★ It moved => the "Cast" column **must not have it anymore**.
        ok(f'C3b ★★★ 「演员·{nm}」行**不在「剧组」那一栏了**'
           '（2026-10-17 搬到「在场人物」：同一个人在两栏各占一行 = 看着像两个人）',
           key not in crew_keys, f'crew_keys={sorted(crew_keys)}')

    # ── C4 角色级"在岗"计数不含子 Agent（提示仍说"3 位在岗"而非含角色）──
    # [EN] C4 role-level "onduty" count excludes sub-agents (hint still "3 onduty")
    onduty_role = sum(1 for r in rows
                      if r['state'] == 'onduty' and not r.get('is_sub'))
    ok('C4 ★★ 角色级"在岗"计数不含子 Agent'
       '（导演/演员/群众演员 3 位，不把"演员·林黛玉"算进去）',
       onduty_role == 3, f'onduty_role={onduty_role}')

    # ── C5 台账 Markdown 也会渲染角色子行、且**不抛错**（这次真回归点）──
    #    `ledger_md()` 对每行都取 `r['runs']`/`r['fails']`，子条目若漏了这两个键
    #    会 KeyError → `_save_note` 吞掉 → `剧组台账.md` 写不出来（A6 缺这一份）。
    # [EN] C5 ledger_md also renders the character sub-rows and **does not raise**
    # [EN] (this is the real regression point). ledger_md reads r['runs']/r['fails']
    # [EN] per row; a sub-item missing those keys KeyErrors -> _save_note swallows it
    # [EN] -> 剧组台账.md never written (A6 misses that file).
    try:
        md = st.ledger_md()
        md_ok = True
        md_err = ''
    except Exception as e:                                       # noqa: BLE001
        md_ok = False
        md_err = repr(e)
    ok('C5 ★★★ `ledger_md()` 在挂了角色子 Agent 时仍**不抛错**'
       '（`剧组台账.md` 才能正常落盘）',
       md_ok, md_err)
    if md_ok:
        ok('C5b 台账 Markdown 里真的出现了「演员·林黛玉」「演员·贾宝玉」两行',
           '演员·林黛玉' in md and '演员·贾宝玉' in md,
           '角色行没进台账' if ('演员·林黛玉' not in md) else 'ok')

    # ── C6 角色"这一拍在动"→ 暖金高亮（用户 2026-10-16 选"角色行动时高亮"）──
    #    `busy` 由 `world.actor_think_at` 的时间戳窗口决定（见 `ledger`）。
    #    近期时间戳 ⇒ `busy=True` ⇒ 面板暖金高亮、文字"出工中"；
    #    过期时间戳 ⇒ `busy=False` ⇒ 恢复"在岗"、不高亮。
    # [EN] C6 character "moving this beat" -> warm-gold highlight (user 2026-10-16 "highlight on action").
    # [EN] `busy` is decided by the timestamp window in `world.actor_think_at` (see `ledger`).
    # [EN] recent timestamp => busy=True => warm-gold highlight + "出工中"; stale => busy=False => "在岗".
    st.world.actor_think_at['林黛玉'] = time.monotonic()        # 刚刚决策完
    led2 = {r['key']: r for r in st.ledger()}
    ok('C6 ★★★ 角色最近决策完成在窗口内 → 该行 `busy=True`（应高亮）',
       led2['actor::林黛玉']['busy'] is True,
       f"busy={led2['actor::林黛玉']['busy']}")
    # ★ 2026-10-17：角色行在「在场人物」那一栏了 ⇒ 刷的是 `_refresh_char_panel`。
    # [EN] ★ 2026-10-17: the character rows are in "On-stage Characters" => we refresh via
    # [EN] `_refresh_char_panel`.
    app._refresh_char_panel()
    controls2 = app._ui_run['char_list'].controls
    rows2 = [r for r in st.ledger() if r.get('is_sub')]
    by_key2 = {r['key']: (r, ctrl) for r, ctrl in zip(rows2, controls2)}
    _cr, _cc = by_key2.get('actor::林黛玉', (None, None))
    _hl = (isinstance(getattr(_cc, 'content', None), ft.Container)
           and getattr(_cc.content, 'bgcolor', None) == app.CREW_BUSY_BG)
    ok('C6b ★★★ 面板里「演员·林黛玉」正在出工时显示**暖金高亮**'
       '（Container + CREW_BUSY_BG）', _hl,
       type(getattr(_cc, 'content', None)).__name__)
    _blob2 = ' | '.join(_texts(_cc)) if _cc is not None else ''
    ok('C6c 高亮时文字显示"出工中 · 正在做"，不再写"在岗"',
       ('出工中' in _blob2) and ('在岗' not in _blob2), _blob2)
    # 过期时间戳 ⇒ 恢复"在岗"（不高亮）
    # [EN] stale timestamp => revert to "在岗" (no highlight)
    st.world.actor_think_at['林黛玉'] = time.monotonic() - 100.0
    led3 = {r['key']: r for r in st.ledger()}
    ok('C6d ★★ 决策时间戳过期（>窗口）→ `busy=False`（恢复"在岗"，不高亮）',
       led3['actor::林黛玉']['busy'] is False,
       f"busy={led3['actor::林黛玉']['busy']}")
    app._refresh_char_panel()
    controls3 = app._ui_run['char_list'].controls
    rows3 = [r for r in st.ledger() if r.get('is_sub')]
    by_key3 = {r['key']: (r, ctrl) for r, ctrl in zip(rows3, controls3)}
    _cr3, _cc3 = by_key3.get('actor::林黛玉', (None, None))
    _hl3 = (isinstance(getattr(_cc3, 'content', None), ft.Container)
            and getattr(_cc3.content, 'bgcolor', None) == app.CREW_BUSY_BG)
    ok('C6e 过期后该行**不再高亮**（退回普通 Row）', not _hl3,
       type(getattr(_cc3, 'content', None)).__name__)


# ══════════════════════════════════════════════════════════════
#  D —— 开拍即标在岗（接线，AST）
# [EN] D -- shoot-open wires mark_onduty (AST)
# ══════════════════════════════════════════════════════════════
def wiring_checks() -> None:
    loop_src = (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')
    tree = ast.parse(loop_src)
    rl = next((n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == 'RunLoop'), None)
    ok('C0 ★ `RunLoop` 类存在', rl is not None, '')
    if rl is None:
        return
    open_day_methods = 0
    marked_methods = 0
    for m in rl.body:
        if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        src = ast.unparse(m)
        if 'await self._open_day()' in src:
            open_day_methods += 1
            if 'self.studio.mark_onduty()' in src:
                marked_methods += 1
    ok('C1 ★★★ 每个调 `await self._open_day()` 的 `RunLoop` 方法，'
       '都在其后调了 `self.studio.mark_onduty()`'
       '（跨天分支 + 第一天分支两处都接上，开拍即把常驻岗标在岗）',
       open_day_methods >= 1 and marked_methods == open_day_methods,
       f'调 _open_day 的方法 {open_day_methods} 个，其中调 mark_onduty 的 {marked_methods} 个')


# ══════════════════════════════════════════════════════════════
async def main(page) -> int:
    print('\n── A mark_onduty 真的把三者标成 onduty ──')
    try:
        logic_checks()
    except Exception:                                            # noqa: BLE001
        ok('A 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── B _refresh_crew_panel 照实显示（行为）──')
    try:
        panel_checks()
    except Exception:                                            # noqa: BLE001
        ok('B 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── C 「演员」按在场角色展开成子 Agent ──')
    try:
        char_checks()
    except Exception:                                            # noqa: BLE001
        ok('C 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])

    print('\n── D 开拍即标在岗（接线 AST）──')
    try:
        wiring_checks()
    except Exception:                                            # noqa: BLE001
        ok('D 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])

    rep = {'checks': report['checks'],
           'passed': sum(1 for c in report['checks'] if c['ok']),
           'total': len(report['checks'])}
    rep['ok'] = rep['passed'] == rep['total']
    (OUT / 'crew_onduty_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n常驻岗在岗验证：{rep['passed']}/{rep['total']}")
    # ★★★ **退出码必须真的出去**（2026-10-28 修）。
    #   原来只在 `page is not None` 时把 code 交给 `shutdown()`，
    #   而这一支**恰恰是按"无头"跑的**（`main(None)`）⇒ **退出码永远是 0** ⇒
    #   它在 `tools/run_all_verifications.py` 里**恒绿**：断言红成一片也没人看得见。
    #   （2026-10-28 实测：把第 136 行的条件改成 `False`，退出码仍是 0。）
    #   ⇒ 现在 `main()` **返回**退出码，由 `__main__` 交给 `sys.exit`。
    # [EN] ★★★ The exit code must actually leave the process (fixed 2026-10-28). It used to be
    # [EN] handed to `shutdown()` only when `page is not None`, yet this criterion runs **headless**
    # [EN] (`main(None)`) => the exit code was always 0 => **always green** in the regression
    # [EN] (measured 2026-10-28: forcing an assertion to `False` still exited 0).
    code = 0 if rep['ok'] else 2
    if page is not None:
        await shutdown(page, code=code)
    return code


if __name__ == '__main__':
    # 本验证不依赖显示（不截图、不接真 page），直接按无头跑最快最稳。
    # [EN] This verification does not depend on a display; run headless.
    sys.exit(asyncio.run(main(None)))
