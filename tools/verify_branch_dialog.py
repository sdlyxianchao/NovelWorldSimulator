# -*- coding: utf-8 -*-
"""验证：岔路口面板（**单选 + 自定义走向 + 5 分钟倒计时 + 简介块**）。

用户 2026-10-07 提了五条，全部落在这支脚本里：

  ① 「这种关键分叉口的对话框 应该在最下面有一个文本框 用户可以自己输入内容
     替代几个选项」        → A 组（主循环收得下、真的影响故事）+ B/C 组（真有那个框）
  ② 「上面应该有一小块简单介绍下当前故事发展 让用户知道大概是怎么回事 要怎么选」
                          → B/C 组（简介块真的在手选之前、内容非空）
  ③ 「下面的倒计时太短了 要设置长一些 比如5分钟 让用户有时间思考」
                          → A 组（默认值）+ B 组（文案会报分秒）
  ④ 「几个按钮不应该是点了就确定 应该只是标签 前面有单选框 然后下面有确定按钮」
                          → B 组（候选是 Radio、**不是**按钮；有「确定」）
  ⑤ 「确定右边才是 不挑了，按策略自动决定」  → C 组（像素量左右顺序）

四层判据：
  A **主循环**：`choose_branch_custom` 与候选那条路**落到同一个地方**
    （事件流 + `director.branch_hint`）—— 否则"自己写"就只剩屏幕上那句话。
    空白输入不算、两条路互斥、等待循环两条路都能唤醒。
  B **结构**（真机控件树）：候选是 Radio 不是按钮、输入框在、两个按钮顺序、
    「确定」初始是灰的、简介块在候选之前。
  C **像素**（真机，标记色法）：单选钮 / 输入框 / 两个按钮**真的画出来了**，
    输入框在按钮**上方**，且「确定」在左。
  D **文案**：新文案中英都有（`i18n_check` 扫不到的是"取值"类，这里手工钉）。

用法：.venv\\Scripts\\python.exe tools/verify_branch_dialog.py [--logic-only]
产出：assets/screenshots/branch_dialog_report.json

English:
Verification: branch dialog panel (**radio selection + custom direction + 5-minute countdown +
intro block**).
The user raised five points on 2026-10-07, all of which land in this script:
  ① "This kind of key branch dialog should have a text box at the very bottom so the user can enter their own content
     to replace the options"        → Group A (main loop accepts it, actually affects the story) + Group B/C (that box really exists)
  ② "There should be a small intro above briefly explaining the current story development so the user knows roughly what's going on and how to choose"
                          → Group B/C (the intro block really comes before manual selection, and its content is non-empty)
  ③ "The countdown below is too short, set it longer, e.g. 5 minutes, so the user has time to think"
                          → Group A (default value) + Group B (copy reports minutes and seconds)
  ④ "The buttons should not confirm on click; they should just be labels with a radio button in front, and then a confirm button below"
                          → Group B (candidates are Radio, **not** buttons; there is a "Confirm")
  ⑤ "To the right of Confirm is 'don't pick, let strategy decide automatically'"  → Group C (pixel measurement of left/right order)
Four layers of criteria:
  A **Main loop**: `choose_branch_custom` and the candidate path **land in the same place**
    (event stream + `director.branch_hint`) — otherwise "write your own" is just that one line on screen.
    Blank input doesn't count, the two paths are mutually exclusive, the wait loop can be woken by either path.
  B **Structure** (real-device control tree): candidates are Radio not buttons, the input box exists, order of the two buttons,
    "Confirm" is initially gray, the intro block comes before the candidates.
  C **Pixels** (real device, marker-color method): the radio buttons / input box / two buttons **are actually drawn**,
    the input box is **above** the buttons, and "Confirm" is on the left.
  D **Copy**: the new copy exists in both Chinese and English (what `i18n_check` can't catch is the "value" kind; pin it manually here).
Usage: .venv\\Scripts\\python.exe tools/verify_branch_dialog.py [--logic-only]
Output: assets/screenshots/branch_dialog_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')          # 本脚本一个真请求都不发
# [EN] This script does not send a single real request

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

ROWS = [
    {'id': 'B1', '标题': '当面揭穿掌柜', '后果': '信任当场崩掉', '权重': 0.5},
    {'id': 'B2', '标题': '夜里走一趟阴司', '后果': '拿到线索，但要欠人情', '权重': 0.3},
    {'id': 'B3', '标题': '先看谁先动', '后果': '张力继续积', '权重': 0.2},
]


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


# ══════════════════════════════════════════════════════════════
#  桩（与 `verify_branch` 同一套形状：闸门要拿真 WorldState，
#  免得 `_push_narrative` 里缺字段炸掉）
# [EN] Stub (same shape as `verify_branch`: the gate wants a real WorldState,
# [EN] otherwise `_push_narrative` will crash on missing fields)
# ══════════════════════════════════════════════════════════════
class FakeWorld:
    def __init__(self, day=1, minutes=0):
        from world.state import GameTime, PersonState, WorldState
        self._w = WorldState()
        self._w.scene = '临河茶肆'
        gt = GameTime()
        gt.minutes = minutes
        gt.day = day
        self._w.clock = gt
        self._w.people = {
            '阿九': PersonState(name='阿九', location='临河茶肆', role='前台'),
            '阿福': PersonState(name='阿福', location='后院', role='前台'),
        }
        self._w.progress_nodes = [
            {'id': 'N1', '名称': '楼前失忆', '概要': '阿福初到', '完成判据': '被收留'},
        ]
        self._w.current_node = 'N1'
        self._w.tension = 0.2

    def __getattr__(self, item):
        return getattr(self._w, item)

    def __setattr__(self, k, v):
        if k == '_w':
            object.__setattr__(self, k, v)
        else:
            setattr(self._w, k, v)


class FakeDB:
    def __init__(self):
        self.events: list[tuple] = []

    def recent_events(self, n=5):
        return [{'content': c} for _a, c in self.events[-n:]]

    def add_event(self, eid, content, etype, day, involved, node):
        self.events.append((etype, content))


class FakeDirector:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = 0
        self.branch_hint = ''

    def is_climax_day(self):
        return False

    async def propose_branches(self):
        self.calls += 1
        return list(self.rows)

    def pick_branch(self, rows, policy=None):
        from director.engine import DirectorEngine as DE
        return DE.pick_branch(rows, policy)


def make_loop(world, db, director):
    from sim.loop import RunLoop

    class P:
        def __init__(self, name, ps):
            self.name = name
            self.ps = ps

    class Disp:
        async def enqueue_narrative(self, *a, **k):
            pass

    class RunFold:
        pass

    loop = RunLoop.__new__(RunLoop)
    loop.world = world
    loop.db = db
    loop.director = director
    loop.runfolder = RunFold()
    loop.agents = [P('阿九', world.people['阿九']), P('阿福', world.people['阿福'])]
    loop.display = Disp()
    loop._cb_warned = set()
    loop._on_status = None
    loop._on_branch = None
    loop._running = True
    loop._paused = False
    loop._branch_pending = False
    loop._last_branch_day = -1
    loop._branch_hint = ''
    loop._branch_choice = None
    loop._branch_custom = ''
    loop._notes = []
    loop._on_narrative = lambda text, pri, kind='': loop._notes.append(text)
    return loop


# ══════════════════════════════════════════════════════════════
#  A. 主循环：自定义走向
# [EN] A. Main loop: custom direction
# ══════════════════════════════════════════════════════════════
def test_custom() -> bool:
    ok = True
    saved = {k: CFG.raw(k) for k in ('BRANCH_WAIT_SECONDS', 'BRANCH_AUTO_POLICY')}
    try:
        CFG.set('BRANCH_AUTO_POLICY', 'first')     # 策略会挑 B1
        # [EN] Strategy will pick B1

        # ① 用户自己写一句 → **优先于策略、也优先于候选**
        # [EN] ① User writes their own line → **takes priority over strategy, and over candidates**
        w, db = FakeWorld(), FakeDB()
        d = FakeDirector(ROWS)
        loop = make_loop(w, db, d)
        CFG.set('BRANCH_WAIT_SECONDS', '6')

        def cb(branches):
            loop.choose_branch_custom('让阿枝自己把那天看见的人说出来')
        loop._on_branch = cb
        loop._branch_pending = True
        got = asyncio.run(loop._maybe_branch(4))
        ok &= rec('A1 ★★★ 自己写的走向**真的生效**（不是只写一行日志）',
                  got is True and d.branch_hint == '让阿枝自己把那天看见的人说出来',
                  repr(d.branch_hint))
        ok &= rec('A1 ★★ 而且**落进事件流**（下一拍导演读得到它）'
                  '—— 与"挑候选"走的是同一个落点',
                  any('走向' in e[0] and '阿枝' in e[1] for e in db.events),
                  str(db.events))
        ok &= rec('A1 ★★ 播报要**分得清**是谁定的（自己写 vs 导演给）',
                  any('你自己定了走向' in n for n in loop._notes),
                  ' | '.join(loop._notes)[:120])
        ok &= rec('A1 ★ 用掉之后要清干净（否则下一次岔路口会自动选回这一句）',
                  loop._branch_custom == '', repr(loop._branch_custom))

        # ② 空白输入 → 当作没写（不能把上一次的选择顶掉，也不能算"用户回话"）
        # [EN] ② Blank input → treated as not written (must not override the previous choice, and must not
        # [EN] count as "user replied")
        w2, db2 = FakeWorld(), FakeDB()
        d2 = FakeDirector(ROWS)
        loop2 = make_loop(w2, db2, d2)
        loop2._branch_custom = '上一轮的旧话'
        loop2.choose_branch_custom('   ')
        ok &= rec('A2 ★★ 空白输入 = 没写（不清空、也不算回话 ——'
                  '清了就等于"你写了但不算数"）',
                  loop2._branch_custom == '上一轮的旧话',
                  repr(loop2._branch_custom))

        # ③ 两条路互斥：先写一句、再点候选 → 候选赢
        # [EN] ③ The two paths are mutually exclusive: write a line first, then click a candidate → candidate
        # [EN] wins
        loop2.choose_branch_custom('写一句')
        loop2.choose_branch('B2')
        ok &= rec('A2 ★★ 两条路互斥（点候选会把"自己写的"清掉，'
                  '否则下一拍会拿旧文本行事）',
                  loop2._branch_custom == '' and loop2._branch_choice == 'B2',
                  f'custom={loop2._branch_custom!r} choice={loop2._branch_choice!r}')

        # ④ 等待循环：**自己写**也要能把它唤醒（不能白等满 5 分钟被策略覆盖）
        # [EN] ④ Wait loop: **writing your own** must also be able to wake it (must not wait the full 5 minutes
        # [EN] and then get overridden by strategy)
        w3, db3 = FakeWorld(), FakeDB()
        d3 = FakeDirector(ROWS)
        loop3 = make_loop(w3, db3, d3)
        CFG.set('BRANCH_WAIT_SECONDS', '30')       # 真等 30 秒才能分出胜负
        # [EN] Really wait 30 seconds to let the winner emerge
        waited: list = []

        # ⚠ 回调必须是**同步函数**（产品就是同步调它的）。写成 `async def` 会
        #   返回一个没人 await 的协程 —— 表现是"白等满 BRANCH_WAIT_SECONDS"，
        #   而那正好是这条判据要抓的现象，会把自己绕进去（第一版就这么绕的）。
        # [EN] ⚠ Callback must be a **synchronous function** (the product calls it synchronously). Writing it
        # [EN] as `async def` will
        # [EN] return a coroutine that nobody awaits — the symptom is "waiting the full BRANCH_WAIT_SECONDS for
        # [EN] nothing",
        # [EN] and that is exactly the phenomenon this criterion is meant to catch, so you'd trap yourself (the
        # [EN] first version did exactly that).
        async def _late():
            await asyncio.sleep(0.6)
            loop3.choose_branch_custom('自己写的那条')

        def cb3(branches):
            asyncio.ensure_future(_late())
        loop3._on_branch = cb3
        loop3._branch_pending = True
        _t0 = time.monotonic()
        asyncio.run(loop3._maybe_branch(5))
        _elapsed = time.monotonic() - _t0
        ok &= rec('A2 ★★★ 等待循环**两条路都认**（自己写也能立刻唤醒，'
                  '不用干等满 `BRANCH_WAIT_SECONDS`）',
                  d3.branch_hint == '自己写的那条' and _elapsed < 10,
                  f'{d3.branch_hint!r} 用时 {_elapsed:.1f}s')

        # ⑤ 默认值：5 分钟（用户点名"比如5分钟"）
        # [EN] ⑤ Default: 5 minutes (the user explicitly said "e.g. 5 minutes")
        from config import SPEC
        ok &= rec('A3 ★★ `BRANCH_WAIT_SECONDS` 默认 300 秒（5 分钟）'
                  '—— 用户：「倒计时太短了 要设置长一些 比如5分钟」',
                  int(SPEC['BRANCH_WAIT_SECONDS']['default']) == 300,
                  str(SPEC['BRANCH_WAIT_SECONDS']['default']))

        # ⑥ 没有界面时不空等（老行为不许被这次改动弄坏）
        # [EN] ⑥ Do not idle-wait when there is no UI (old behavior must not be broken by this change)
        w4, db4 = FakeWorld(), FakeDB()
        d4 = FakeDirector(ROWS)
        loop4 = make_loop(w4, db4, d4)
        CFG.set('BRANCH_WAIT_SECONDS', '0')
        loop4._on_branch = None
        loop4._branch_pending = True
        got4 = asyncio.run(loop4._maybe_branch(6))
        ok &= rec('A3 ★ 没有界面监听时**照样不空等**（照旧直接按策略挑）',
                  got4 is True and d4.branch_hint == '当面揭穿掌柜',
                  repr(d4.branch_hint))
    finally:
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


# ══════════════════════════════════════════════════════════════
#  B/C/D. 真机（控件树 + 像素 + 文案）
# [EN] B/C/D. Real device (control tree + pixels + copy)
# ══════════════════════════════════════════════════════════════
def _walk(root, out=None) -> list:
    out = [] if out is None else out
    if root is None:
        return out
    out.append(root)
    for a in ('controls', 'content', 'actions'):
        v = getattr(root, a, None)
        if isinstance(v, list):
            for c in v:
                _walk(c, out)
        elif v is not None and hasattr(v, '__class__'):
            _walk(v, out)
    return out


def _texts(root, out=None) -> list:
    out = [] if out is None else out
    for c in _walk(root):
        import flet as ft
        if isinstance(c, ft.Text) and c.value:
            out.append(str(c.value))
        if isinstance(c, ft.TextField) and c.hint_text:
            out.append(str(c.hint_text))
        if isinstance(c, ft.Radio) and c.label:
            out.append(str(c.label))
        if isinstance(c, ft.Markdown) and c.value:
            out.append(str(c.value))
        inner = getattr(c, 'content', None)
        if isinstance(inner, str):
            out.append(inner)
    return out


async def gui_main(page) -> int:
    import flet as ft
    from types import SimpleNamespace
    from PIL import Image

    from gui.app_flet import NovelWorldApp
    from i18n import set_lang
    set_lang('zh')

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.6)

    class FakeW:
        game_day = 7
        scene = '临河茶肆'
        def clock_display(self): return '戌时三刻'
        def on_stage_names(self): return ['主角', '阿枝']
        def current_node_info(self):
            return {'id': 'N3', '名称': '旧事浮头', '概要': '线索开始对不上',
                    '完成判据': '两人说法不一'}

    class FakeL:
        world = FakeW()
        branch_hint = ''
        def __init__(self): self.got = []
        def _recap_text(self): return '前几日那笔对不上的账越查越深。'
        def choose_branch(self, bid): self.got.append(('id', bid))
        def choose_branch_custom(self, text): self.got.append(('text', text))

    loop = FakeL()
    app.session = SimpleNamespace(loop=loop)
    app._on_branch(ROWS)
    await asyncio.sleep(1.0)

    ok = True
    ui = getattr(app, '_branch_ui', None)
    ok &= rec('B0 ★★ 面板真的建起来了（`_branch_ui` 有句柄）', bool(ui), str(bool(ui)))
    if not ui:
        return 2
    dlg = ui['dlg']
    all_txt = _texts(dlg)

    # ── B 结构 ──
    # [EN] ── B structure ──
    radios = [c for c in _walk(dlg) if isinstance(c, ft.Radio)]
    groups = [c for c in _walk(dlg) if isinstance(c, ft.RadioGroup)]
    fields = [c for c in _walk(dlg) if isinstance(c, ft.TextField)]
    btns = [c for c in _walk(dlg)
            if isinstance(c, (ft.FilledButton, ft.TextButton))]
    ok &= rec('B1 ★★★ 候选是**单选钮**（用户：「几个按钮不应该是点了就确定 '
              '应该只是标签 前面有单选框」）',
              len(radios) == len(ROWS) and len(groups) == 1,
              f'Radio={len(radios)} RadioGroup={len(groups)}')
    ok &= rec('B1 ★★ 候选**不再是按钮**（点了就定的那种一个都不许留）',
              len(btns) == 2, f'按钮 {len(btns)} 个：{[_btn_label(b) for b in btns]}')
    ok &= rec('B1 ★★ 但要有「确定」（用户：「然后下面有确定按钮」）',
              any('确' in _btn_label(b) for b in btns),
              str([_btn_label(b) for b in btns]))
    ok &= rec('B2 ★★★ 最下面有**自己输入**的文本框（用户：「最下面有一个文本框 '
              '用户可以自己输入内容 替代几个选项」）',
              len(fields) == 1 and bool(getattr(fields[0], 'multiline', False)),
              f'输入框 {len(fields)} 个 multiline='
              f'{getattr(fields[0], "multiline", None) if fields else None}')
    ok &= rec('B2 ★★ 输入框的提示语说清了它**优先于**上面的候选',
              any('以它为准' in x for x in all_txt),
              str([x for x in all_txt if '以它为准' in x])[:110])
    ok &= rec('B3 ★★★ 上面有「当前故事发展」那一小块（用户：'
              '「上面应该有一小块简单介绍下当前故事发展」）',
              any(('第 7 天' in x and '临河茶肆' in x) for x in all_txt),
              str([x for x in all_txt if '第 7 天' in x])[:110])
    ok &= rec('B3 ★★ 简介块里有**当前节点**与**前情**（光有天数等于没说）',
              any('◈' in x for x in all_txt) and any('前情' in x for x in all_txt),
              str([x for x in all_txt if '◈' in x or '前情' in x])[:130])
    # 简介必须在候选**之前**（先看懂再选，顺序反了等于没介绍）
    # [EN] The intro must come **before** the candidates (understand first, then choose; reversed order
    # [EN] means no intro at all)
    i_intro = next((i for i, x in enumerate(all_txt) if '前情' in x), -1)
    i_opt = next((i for i, x in enumerate(all_txt) if x.startswith('B1')), -1)
    ok &= rec('B3 ★★ 简介排在候选**之前**（顺序反了就等于没介绍）',
              i_intro >= 0 and i_opt > i_intro, f'前情@{i_intro} 候选@{i_opt}')
    # 输入框必须在**最下面**（用户原话：「应该在最下面有一个文本框」）
    # [EN] The input box must be at the **very bottom** (user's own words: "there should be a text box at
    # [EN] the very bottom")
    i_field = next((i for i, x in enumerate(all_txt) if '以它为准' in x), -1)
    ok &= rec('B3 ★★ 那个文本框排在候选**之后**（用户要的是"**最下面**有一个文本框"，'
              '挪到上面就不算）',
              i_field > i_opt >= 0, f'输入框@{i_field} 候选@{i_opt}')
    ok &= rec('B4 ★★ 倒计时按**分钟**报（5 分钟写成"300 秒"没人算得过来）',
              any(('分' in x and '秒' in x) for x in all_txt),
              str([x for x in all_txt if '还剩' in x]))

    # ── 交互：确定初始灰 → 选中后亮 → 点了才生效 ──
    # [EN] ── Interaction: OK is initially gray → lights up after selection → only takes effect when
    # [EN] clicked ──
    ok &= rec('B5 ★★★ 一进来「确定」是**灰的**（没选也没写 —— 免得点了什么都不发生）',
              bool(ui['confirm'].disabled) is True,
              f'disabled={ui["confirm"].disabled}')
    ui['group'].value = 'B2'
    ui['group'].on_change(None)
    page.update()
    await asyncio.sleep(0.3)
    ok &= rec('B5 ★★★ 选了候选 → 「确定」变可点（单选只是标签，'
              '**点了确定才算数**）',
              ui['confirm'].disabled is False and loop.got == [],
              f'disabled={ui["confirm"].disabled} got={loop.got}')
    ok &= rec('B6 ★★★ 倒计时**看到用户动手就停表**（否则到点会把他写的那句丢掉）',
              ui['state']['touched'] is True and '停止自动决定' in str(ui['countdown'].value),
              f'touched={ui["state"]["touched"]} 文案={ui["countdown"].value!r}')
    ui['confirm'].on_click(None)
    await asyncio.sleep(0.4)
    ok &= rec('B6 ★★ 点「确定」→ 主循环**真的收到**那个 id',
              loop.got == [('id', 'B2')] and ui['state']['done'] is True,
              str(loop.got))

    # ── 自定义输入优先 ──
    # [EN] ── Custom input takes priority ──
    app._on_branch(ROWS)
    await asyncio.sleep(0.7)
    ui2 = app._branch_ui
    ui2['group'].value = 'B1'                      # 故意同时选了候选
    # [EN] Deliberately selected a candidate at the same time
    ui2['custom'].value = '让阿枝自己说出来'
    ui2['custom'].on_change(None)
    page.update()
    await asyncio.sleep(0.3)
    ui2['confirm'].on_click(None)
    await asyncio.sleep(0.4)
    ok &= rec('B7 ★★★ 既选了候选、又写了字 → **以写的为准**'
              '（主循环口径一致：作者亲口说的最硬）',
              loop.got[-1] == ('text', '让阿枝自己说出来'), str(loop.got[-1:]))

    # ── C 像素：标记色法（只动颜色，不动几何）──
    # [EN] ── C pixels: marker-color method (only change color, not geometry) ──
    app._on_branch(ROWS)
    await asyncio.sleep(0.9)
    ui3 = app._branch_ui
    undo: list = []

    def paint(ctrl, hexs):
        for attr in ('border_color', 'bgcolor', 'active_color'):
            if hasattr(ctrl, attr) and getattr(ctrl, attr) is not None:
                undo.append((ctrl, attr, getattr(ctrl, attr)))
                setattr(ctrl, attr, hexs)
                return
        inner = getattr(ctrl, 'content', None)
        if isinstance(inner, ft.Text):
            undo.append((inner, 'color', inner.color))
            inner.color = hexs

    for r in [c for c in _walk(ui3['dlg']) if isinstance(c, ft.Radio)]:
        old = r.label_style
        undo.append((r, 'label_style', old))
        r.label_style = ft.TextStyle(size=(old.size if old else 13.5),
                                    color='#ff00ff')
    paint(ui3['custom'], '#00ffff')
    paint(ui3['confirm'], '#ffff00')
    paint(ui3['auto'], '#00ff00')
    page.update()
    await asyncio.sleep(0.6)
    png = await page.take_screenshot()
    shot = OUT / 'branch_dialog.png'
    shot.write_bytes(png or b'')
    im = Image.open(shot).convert('RGB')
    px = im.load()
    W, H = im.size

    def find(rgb, tol=40):
        x0 = y0 = 10 ** 9
        x1 = y1 = -1
        n = 0
        for y in range(0, H, 2):
            for x in range(0, W, 2):
                c = px[x, y]
                if all(abs(c[i] - rgb[i]) <= tol for i in range(3)):
                    n += 1
                    x0, y0 = min(x0, x), min(y0, y)
                    x1, y1 = max(x1, x), max(y1, y)
        return (n, (x0, y0, x1, y1) if n else None)

    n_radio, bb_radio = find((255, 0, 255))
    n_field, bb_field = find((0, 255, 255))
    n_ok, bb_ok = find((255, 255, 0))
    n_auto, bb_auto = find((0, 255, 0))
    print(f'\n  像素：radio={n_radio}{bb_radio} field={n_field}{bb_field}\n'
          f'        confirm={n_ok}{bb_ok} auto={n_auto}{bb_auto}')

    ok &= rec('C1 ★★★ 单选钮**真的画在屏幕上**（树里有 ≠ 看得见）',
              n_radio > 40, f'{n_radio} px {bb_radio}')
    ok &= rec('C2 ★★★ 那个文本框**真的画出来了**'
              '（多行 TextField 不给 height 会塌成 0，实测一个像素都没有）',
              n_field > 5, f'{n_field} px {bb_field}')
    ok &= rec('C3 ★★★ 「确定」与「不挑了」两个按钮都在',
              n_ok > 40 and n_auto > 20, f'confirm={n_ok} auto={n_auto}')
    if bb_ok and bb_auto:
        ok &= rec('C3 ★★★ 顺序 = 用户点名的「确定右边才是 不挑了」'
                  '（确定在**左**）',
                  bb_ok[0] < bb_auto[0], f'确定 x={bb_ok[0]} 不挑了 x={bb_auto[0]}')
    else:
        ok &= rec('C3 ★★★ 顺序判据拿不到 bbox（两个按钮没都画出来）', False,
                  f'{bb_ok} {bb_auto}')
    if bb_field and bb_ok:
        ok &= rec('C4 ★★ 文本框在按钮**上方**（"最下面那个框"要看得见，'
                  '不能要滑一下）',
                  bb_field[3] < bb_ok[1], f'框底 y={bb_field[3]} 按钮顶 y={bb_ok[1]}')
    else:
        ok &= rec('C4 ★★ 文本框/按钮位置拿不到', False, f'{bb_field} {bb_ok}')

    for ctrl, attr, old in undo:
        setattr(ctrl, attr, old)
    page.update()

    # ── D 文案 ──
    # [EN] ── D copy ──
    from i18n import _ZH2EN
    set_lang('en')
    from i18n import t as _t
    keys = ('岔路口 · 往哪走', '确 定', '自己定一个走向', '第 {d} 天 · {scene}',
            '前情：{x}', '已停止自动决定 —— 你正在选，选好点「确定」',
            '还剩 {m} 分 {s} 秒，之后按策略自动决定')
    miss = [k for k in keys if _t(k) == k]
    ok &= rec('D1 ★★ 新文案的中英**都登记了**（动态取值 `i18n_check` 扫不到，'
              '这里手工钉）', not miss, f'缺译：{miss}')
    set_lang('zh')
    return 0 if ok else 2


def _btn_label(b) -> str:
    import flet as ft
    inner = getattr(b, 'content', None)
    if isinstance(inner, ft.Text):
        return str(inner.value or '')
    return str(inner or '')


def _finish(code: int = 0) -> int:
    """算总数、写报告、打印小结 —— **必须在 `shutdown()` 之前调**。

    ⚠ `shutdown()` 内部会 `os._exit`，写在它之后的收尾**一行都不会执行**
    （本项目 §40.0 那条：41 个脚本的 `exit_now(0 if ok else 2)` 全是死代码）。
    第一版就是写在 `ft.run()` 之后，于是"报告没更新 + 没有汇总输出"，
    而磁盘上留着一份**上一轮的旧报告**（mtime 只差几秒），看着像刚跑过。
    
        English:
    Compute totals, write the report, print the summary — **must be called before `shutdown()`**.
        ⚠ `shutdown()` calls `os._exit` internally; teardown written after it **won't execute a single line**
        (that rule in §40.0 of this project: the `exit_now(0 if ok else 2)` in 41 scripts is all dead code).
        The first version wrote it after `ft.run()`, so "the report wasn't updated + there was no summary output",
        while a **stale report from the previous run** was left on disk (mtime off by only a few seconds), looking like it had just run.
    """
    head('结果')
    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'branch_dialog_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'  岔路口面板：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'), flush=True)
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"][:120]}]')
    print('-' * 62, flush=True)
    return 0 if report['ok'] else 2


def main() -> int:
    logic_only = '--logic-only' in sys.argv
    head('A. 主循环：自己写的走向')
    test_custom()

    if logic_only:
        return _finish()

    import flet as ft
    from util.flet_shutdown import shutdown, exit_now

    async def entry(page):
        try:
            await gui_main(page)
        except BaseException:
            report['fatal'] = traceback.format_exc()
            print(traceback.format_exc())
        # ★ 收尾必须在 shutdown 之前（它内部 os._exit）
        # [EN] ★ Teardown must come before shutdown (it calls os._exit internally)
        code = _finish()
        await shutdown(page, code=code)

    try:
        ft.run(entry)
    except BaseException:
        report['fatal'] = traceback.format_exc()
        print(traceback.format_exc())
    # 走到这里说明 ft.run 自己回来了（正常路径已被 shutdown 收走）
    # [EN] Reaching here means ft.run returned on its own (the normal path was already taken by shutdown)
    exit_now(_finish())


if __name__ == '__main__':
    main()
