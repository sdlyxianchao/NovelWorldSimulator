# -*- coding: utf-8 -*-
"""验证：**点状态条看"这一发 AI 往来"**（2026-10-24）。

用户原话
--------
    「我希望左下角的状态……显示运行中 等下一次行动 xxxx 做什么 时间s 的这个 panel，
      **我点击了之后弹出一个对话框**，然后显示**当前发送给 LLM 以及 LLM 返回的内容**」

判据分组（一条判据守一道闸）
--------------------------
  A **状态条可点**：整颗胶囊包了手势层、有手型光标、悬停说明说清"点了看什么"
  B **数据层收全文**：`_llm_last` 里是**完整的** messages 与完整正文
     （不是界面日志那份截到 700/1200 字的摘要 —— 摘要里正好缺最要紧的约束）
  C **配对不错**：新的请求到了要**清掉上一发的响应**（否则屏幕上会出现
     "请求是新的、响应是上一条"，那看起来像模型答非所问）
  D **真机对话框**：真的能弹出来，上半是请求全文、下半是响应全文，
     而且**一个字都没截**
  E **轮询有终点**：对话框关掉之后刷新任务自己退出（不能留一个死循环）

跑法：.venv\\Scripts\\python.exe tools/verify_llm_probe.py
产出：assets/screenshots/llm_probe_report.json

English:
Verify **clicking the status pill to inspect this LLM exchange** (2026-10-24).
The user: "the bottom-left status panel showing running / waiting / doing X / N s -- **clicking it
should pop a dialog** showing **what is currently sent to the LLM and what it returned**".
Groups: A the pill is clickable (gesture layer + hand cursor + hover text saying what it shows) /
B the data layer keeps the **full** messages and text (not the 700/1200-char summary the UI log keeps
-- that is where the key constraints get cut) / C pairing is right (a new request **clears** the
previous response, or the screen shows "new request, old response", which reads like the model
answering something else) / D the real dialog opens with the full request on top and the full
response below, **nothing truncated** / E the refresh loop **ends** when the dialog closes (no
leftover loop).
Usage: .venv\\Scripts\\python.exe tools/verify_llm_probe.py
Output: assets/screenshots/llm_probe_report.json
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
from util.flet_shutdown import shutdown                        # noqa: E402
import verify_ui_common as VU                                  # noqa: E402

VU.redirect_env_writes()
from config import CFG                                          # noqa: E402
CFG.set('MOCK_LLM', 'true')
VU.patch_flat_background()

import gui.app_flet as A                                       # noqa: E402
from llm.router import llm                                      # noqa: E402
from i18n import set_lang                                       # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
REPORT = OUT / 'llm_probe_report.json'
_rows: list[dict] = []

#: 造一个**够长**的请求/响应（真实的整理稿 prompt 就是几千到几万字）。
LONG_REQ = '【这一段是长提示词的正文】' + ('这是一条必须被看到的约束。' * 400)
LONG_RESP = '【这一段是模型返回的正文】' + ('他抬手，把灯芯拨亮了一寸。' * 300)


def ok(name: str, cond, detail='') -> bool:
    _rows.append({'判据': name, '通过': bool(cond), '实测': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''))
    return bool(cond)


def _mk_app() -> A.NovelWorldApp:
    app = object.__new__(A.NovelWorldApp)
    app._ui_run = {}
    # ⚠ 夹具是 `object.__new__` 造的（绕过 `__init__`），所以 `__init__` 里那几件
    #   必须**手动补上** —— 少了其中一个，产品里读它就会 `AttributeError`，
    #   而那看起来像"产品坏了"（实测：第一版漏了 `_llm_turns`，B 组当场崩）。
    # [EN] The fixture is built with `object.__new__` (bypassing `__init__`), so the fields set there
    # [EN] must be **filled in by hand** -- missing one raises `AttributeError` inside the product,
    # [EN] which looks like "the product is broken" (measured: the first version missed
    # [EN] `_llm_turns` and group B crashed immediately).
    app._llm_turns = []
    app._llm_probe_on = False
    app._llm_probe_tick_alive = False
    return app


def _emit_req(purpose='crew_day_novel', content=LONG_REQ):
    llm._emit({'type': 'request', 'purpose': purpose, 'model': 'deepseek-flash',
               'tier': 'daily',
               'messages': [{'role': 'system', 'content': '你是作家。'},
                            {'role': 'user', 'content': content}]})


def _emit_resp(text=LONG_RESP, ms=1234, tin=999, tout=888):
    llm._emit({'type': 'response', 'purpose': 'crew_day_novel',
               'model': 'deepseek-flash', 'text': text,
               'ms': ms, 'tin': tin, 'tout': tout})


# ══════════════════════════════════════════════════════════════
#  A —— 状态条可点（源码 + 真机）
# ══════════════════════════════════════════════════════════════
def a_clickable() -> None:
    print('\n【A】状态条可点')
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    ok('A1 ★★★ 状态条**整颗胶囊包了手势层**（`GestureDetector` + `on_tap`）'
       '—— 用户：「我点击了之后弹出一个对话框」',
       'self._run_status_bar = ft.GestureDetector(' in src
       and 'on_tap=lambda e: self.show_llm_probe_dialog()' in src, '')
    # ⚠ **必须限定在状态条那一段**：整份源码里 `mouse_cursor=ft.MouseCursor.CLICK`
    #   出现好几处（小地图、行手势层…），只查全文件的话把手型光标从状态条上
    #   删掉判据照样绿（反例法当场漏掉，第一版就是这么写的）。
    # [EN] ⚠ **Must be scoped to the status-bar block**: `mouse_cursor=ft.MouseCursor.CLICK`
    # [EN] appears several times in the file (minimap, row gestures...), so searching the whole file
    # [EN] stays green even after removing it from the pill (the counterexample caught it).
    _i = src.find('self._run_status_bar = ft.GestureDetector(')
    _seg = src[_i:_i + 1400] if _i >= 0 else ''
    ok('A2 ★★★ 而且**状态条这一段**有手型光标'
       '（不给的话用户看不出它能点 —— "看不出来"等于没做）',
       'mouse_cursor=ft.MouseCursor.CLICK' in _seg, f'片段 {len(_seg)} 字')
    ok('A3 ★★★ 状态条的悬停说明**说清"点了会看到什么"**（这一颗上只写状态，'
       '没人猜得到它还能打开 AI 往来）',
       'show_llm_probe_dialog' in _seg and '点一下看' in _seg, '')


# ══════════════════════════════════════════════════════════════
#  B —— 数据层收全文
# ══════════════════════════════════════════════════════════════
def b_full_text() -> None:
    print('\n【B】数据层收全文')
    app = _mk_app()
    app._ensure_llm_probe()
    _emit_req()
    if not app._llm_turns:
        # ⚠ **收不到就报红，不许 IndexError**：直接取 `[-1]` 的话整组会崩，
        #   而"崩了"在反例法里会被读成"漏掉"，让人去查产品（产品其实是对的）。
        # [EN] ⚠ **Report red, don't IndexError**: taking `[-1]` directly crashes the whole group, and
        # [EN] a crash reads as "missed" in the counterexample method, sending you to inspect a product
        # [EN] that is in fact fine.
        ok('B1 ★★★ 请求正文**一个字都没截**—— 前提是"请求真的被记下来了"',
           False, f'`_llm_turns` 是空的（{len(app._llm_turns)} 条）')
        return
    d = app._llm_turns[-1]
    got = str((d.get('messages') or [])[-1].get('content') or '')
    ok('B1 ★★★ 请求正文**一个字都没截**（存的是完整 messages）'
       '—— 界面日志那份截到 700 字，正好会缺掉最要紧的约束',
       got == LONG_REQ, f'{len(got)} 字（原文 {len(LONG_REQ)} 字）')
    _emit_resp()
    ok('B2 ★★★ 响应正文也**一个字都没截**',
       str(app._llm_turns[-1].get('resp') or '') == LONG_RESP,
       f'{len(str(app._llm_turns[-1].get("resp") or ""))} 字')
    ok('B3 ★★ 还记下了这一发的身份（用途 / 模型 / 耗时 / token）'
       '—— 对话框顶上那行就是它',
       app._llm_turns[-1].get('purpose') == 'crew_day_novel'
       and app._llm_turns[-1].get('model') == 'deepseek-flash'
       and int(app._llm_turns[-1].get('ms') or 0) == 1234,
       f'{app._llm_turns[-1].get("purpose")} · '
       f'{app._llm_turns[-1].get("model")} · {app._llm_turns[-1].get("ms")}ms')

    # ★★★ 2026-10-24（用户第二版）：「LLM **一点点返回**的」
    #   `router` 在流式模式下每读到一块发一个 `delta`；只听 `response` 的话，
    #   屏幕上就是"空着几十秒，然后整段砸下来" —— 正好不是用户要的。
    # [EN] ★★★ 2026-10-24 (the user's second version): "what the LLM **returns bit by bit**".
    # [EN] In streaming mode `router` emits a `delta` per chunk; listening to `response` alone means
    # [EN] "blank for tens of seconds, then everything at once" -- exactly not what was asked for.
    app2 = _mk_app()
    app2._ensure_llm_probe()
    _emit_req()
    llm._emit({'type': 'delta', 'stream': 'content', 'text': '第一块',
               'purpose': 'crew_day_novel', 'model': 'deepseek-flash'})
    _n1 = len(str(app2._llm_turns[-1].get('resp') or ''))
    llm._emit({'type': 'delta', 'stream': 'content', 'text': '第二块',
               'purpose': 'crew_day_novel', 'model': 'deepseek-flash'})
    _n2 = len(str(app2._llm_turns[-1].get('resp') or ''))
    ok('B4 ★★★ `delta` 一到就**接进正文**（"一点点长"靠的就是这一步）',
       _n1 == 3 and _n2 == 6, f'第一块后 {_n1} 字 → 第二块后 {_n2} 字')
    llm._emit({'type': 'delta', 'stream': 'reasoning', 'text': '想一想',
               'purpose': 'crew_day_novel', 'model': 'deepseek-flash'})
    ok('B5 ★★ 而 `reasoning`（思考）**不混进正文**（混进去就分不清哪句是它写的）',
       '想一想' not in str(app2._llm_turns[-1].get('resp') or '')
       and '想一想' in str(app2._llm_turns[-1].get('reasoning') or ''), '')


# ══════════════════════════════════════════════════════════════
#  C —— 配对不错
# ══════════════════════════════════════════════════════════════
def c_pairing() -> None:
    print('\n【C】配对不错')
    app = _mk_app()
    app._ensure_llm_probe()
    _emit_req()
    _emit_resp()
    if not app._llm_turns:
        # ⚠ 同 B 组：收不到就**报红**，不许 `IndexError`（崩了会被读成"漏掉"）。
        # [EN] ⚠ Same as group B: report red, never `IndexError` (a crash reads as "missed").
        ok('C1 ★★★ 新的一发是独立的一条 —— 前提是"请求真的被记下来了"',
           False, f'`_llm_turns` 是空的（{len(app._llm_turns)} 条）')
        return
    first_seq = int(app._llm_turns[-1].get('seq') or 0)
    # 新的一发来了（还没回）
    _emit_req(purpose='prose_flow_fix', content='新的请求')
    d = app._llm_turns[-1]
    ok('C1 ★★★ 新的一发是**独立的一条**，不会和上一发混在一起'
       '（聊天窗口里必须是一发一条 —— 混了就成了"请求是新的、响应是上一条"）',
       len(app._llm_turns) == 2 and str(d.get('resp') or '') == ''
       and int(d.get('seq') or 0) > first_seq,
       f'共 {len(app._llm_turns)} 发 · 新一发响应={str(d.get("resp") or "")[:8]!r}')
    ok('C2 ★★ 上一发**留着自己的响应**（能往上翻，不是被盖掉）',
       str(app._llm_turns[0].get('resp') or '') == LONG_RESP,
       f'{len(str(app._llm_turns[0].get("resp") or ""))} 字')
    ok('C3 ★★ 用途跟着换成新的（不能还挂着上一发的用途）',
       d.get('purpose') == 'prose_flow_fix', str(d.get('purpose')))

    # 没有在等的那一发时，别硬塞响应（缓存命中 / Mock 那条路会这样）
    app2 = _mk_app()
    app2._ensure_llm_probe()
    _emit_resp()
    ok('C4 ★★ 没有在等的请求时，响应**不会凭空造一条记录**'
       '（缓存命中 / Mock 会走到这里；硬塞会造出"根本不属于一对"的假象）',
       not app2._llm_turns, f'{app2._llm_turns}')


# ══════════════════════════════════════════════════════════════
#  D/E —— 真机对话框
# ══════════════════════════════════════════════════════════════
def _all_texts(ctl, out=None) -> list[str]:
    out = [] if out is None else out
    try:
        v = getattr(ctl, 'value', None)
        if isinstance(v, str) and v.strip():
            out.append(v)
        kids = getattr(ctl, 'controls', None) or []
        for c in kids:
            _all_texts(c, out)
        c = getattr(ctl, 'content', None)
        if c is not None:
            _all_texts(c, out)
    except Exception:                                            # noqa: BLE001
        pass
    return out



def _bubble_rows(dlg) -> list:
    """对话框里**气泡行**（`Row` 只包一个子控件，且对齐是 START/END 之一）。

    ★ 为什么按这个形状认：`_bubble` 返回的是
      `GestureDetector > Row([Container(气泡)], alignment=END/START)`
      —— "只包一个子控件"能把它和列表行、标题行分开。
    [EN] The dialog's **bubble rows**: a `Row` holding exactly one child, aligned START or END.
    [EN] ★ Why this shape: `_bubble` returns `GestureDetector > Row([Container], alignment=...)`;
    [EN] "exactly one child" separates it from list rows and headings.
    """
    out: list = []
    for c in VU.walk(dlg):
        if not isinstance(c, ft.Row):
            continue
        kids = getattr(c, 'controls', None) or []
        if len(kids) != 1:
            continue
        if str(getattr(c, 'alignment', '')).endswith(('START', 'END')):
            out.append(c)
    return out


def _has_max_lines(dlg, want: int) -> bool:
    """有没有 `max_lines == want` 的 Text（= 长消息默认折叠）。"""
    for c in VU.walk(dlg):
        if isinstance(c, ft.Text) and getattr(c, 'max_lines', None) == want:
            return True
    return False


def _last_resp_len(dlg) -> int:
    """对话框里**最后一条气泡**的文本长度（"一点点长"就量它）。"""
    rows = _bubble_rows(dlg)
    if not rows:
        return 0
    try:
        box = rows[-1].controls[0]          # Container
        col = box.content                   # Column
        txt = col.controls[-1]              # Text
        return len(str(getattr(txt, 'value', '') or ''))
    except Exception:                                            # noqa: BLE001
        return 0


async def de_dialog(page: ft.Page) -> None:
    print('\n【D】真机对话框')
    # ⚠ 这里必须用**真构造**（`NovelWorldApp()` + `main(page)`），
    #   不能用 `object.__new__` 造空壳：`show_main_screen` 第一行就读 `self.page`，
    #   空壳上根本没有这个属性（第一版就是这么崩的，报成"整组没跑完"）。
    # [EN] ⚠ Must use the **real constructor** (`NovelWorldApp()` + `main(page)`), not an
    # [EN] `object.__new__` shell: `show_main_screen` reads `self.page` on its first line, which the
    # [EN] shell simply does not have (the first version crashed exactly there and reported it as
    # [EN] "the whole group did not finish").
    app = A.NovelWorldApp()
    app.main(page)          # ← 这一句里就挂上了 LLM 监听（见 `main` 开头）
    page.update()
    await asyncio.sleep(1.2)
    app.show_main_screen()  # 状态条要真的建出来（用户是从它点开的）
    page.update()
    await asyncio.sleep(1.0)

    _emit_req()
    await asyncio.sleep(0.2)
    app.show_llm_probe_dialog()
    page.update()
    await asyncio.sleep(0.9)

    # ⚠ 对话框在 Flet 1.0 里挂在 `page._dialogs.controls`（不是 `page.dialogs`），
    #   而且**关掉的旧帧还留在里面** ⇒ 必须按 `open` 过滤。
    #   第一版读 `page.dialogs` 恒为空，报成"点一下没弹出" —— 是判据找错了地方。
    # [EN] ⚠ In Flet 1.0 dialogs live in `page._dialogs.controls` (not `page.dialogs`), and
    # [EN] **closed old frames stay in there** => filter by `open`. The first version read
    # [EN] `page.dialogs`, which is always empty, and reported "clicking pops nothing" -- the criterion
    # [EN] was looking in the wrong place.
    _open = VU.open_dialogs(page)
    dlg = _open[-1] if _open else None
    ok('D1 ★★★ 点一下**真的弹出对话框**', dlg is not None,
       f'打开着的对话框 {1 if dlg else 0} 个')
    if dlg is None:
        return
    texts = _all_texts(dlg)
    blob = '\n'.join(texts)

    # ── 形态：**聊天流**（用户第二版的原话就是这个）──
    #   一发 = **两条气泡**：一条"我发的"靠右、一条"它回的"靠左。
    #   ⚠ 判**对齐方向**，不判"有没有两块内容" —— 只判后者的话，
    #     一个上下两栏的老界面也能过（第一版就是那种，用户当场说"不是这个设计"）。
    # [EN] -- Shape: a **chat stream** (the user's second version said exactly this) --
    # [EN] One exchange = **two bubbles**: mine on the right, its reply on the left.
    # [EN] ⚠ Judge the **alignment**, not "are there two blocks": the latter would also pass the old
    # [EN] top/bottom design (the first version), which the user rejected on sight.
    bubbles = _bubble_rows(dlg)
    ok('D2 ★★★ 是**聊天流**：一发两条气泡，一条"我发的"一条"它回的"',
       len(bubbles) >= 2, f'气泡行 {len(bubbles)} 条')
    ok('D3 ★★★ **发给模型的靠右**（用户消息那一侧）',
       bool(bubbles) and str(bubbles[0].alignment).endswith('END'),
       f'{bubbles[0].alignment if bubbles else None}')
    ok('D4 ★★★ **模型返回的靠左**（服务器消息那一侧）',
       len(bubbles) >= 2 and str(bubbles[1].alignment).endswith('START'),
       f'{bubbles[1].alignment if len(bubbles) >= 2 else None}')
    ok('D5 ★★★ 请求**全文**在气泡里（一个字都没截）',
       LONG_REQ in blob, f'最长一块 {max((len(x) for x in texts), default=0)} 字')
    ok('D6 ★★ 长消息**默认折叠到 6 行**（一条 prompt 一万多字，全展开读不下去）',
       _has_max_lines(dlg, A.NovelWorldApp.LLM_BUBBLE_LINES),
       f'期望 max_lines={A.NovelWorldApp.LLM_BUBBLE_LINES}')

    # ── "一点点返回"：delta 来了，气泡里的字要**真的变长** ──
    ok('D7 ★★ 还没回时，下方那条明说**"正在接收…"**（这一行就是"卡住了吗"的答案）',
       '正在接收' in blob or '正在等' in blob, '')
    _before = _last_resp_len(dlg)
    for _chunk in ('他抬手，', '把灯芯拨亮了一寸。'):
        llm._emit({'type': 'delta', 'stream': 'content', 'text': _chunk,
                   'purpose': 'crew_day_novel', 'model': 'deepseek-flash'})
        await asyncio.sleep(0.55)      # 比 0.4s 的刷新长一点
    _after = _last_resp_len(dlg)
    ok('D8 ★★★ **"一点点返回"真的在屏幕上长**（`delta` → 气泡里的字数变多）'
       '—— 只听 `response` 的话是"空几十秒后整段砸下来"',
       _after > _before, f'{_before} → {_after} 字')

    _emit_resp()
    await asyncio.sleep(1.0)
    texts2 = _all_texts(dlg)
    ok('D9 ★★★ 全部回来之后，那条气泡是**完整正文**（不是摘要）',
       LONG_RESP in '\n'.join(texts2),
       f'最长一块 {max((len(x) for x in texts2), default=0)} 字')
    ok('D10 ★★ 顶上那行写了这一发的身份（用途 + 模型 + 状态）',
       '整理当天这一章' in '\n'.join(texts2)
       and 'deepseek-flash' in '\n'.join(texts2), '')

    # ── E：关掉之后刷新任务要自己退出 ──
    # ⚠ 判**任务还活着吗**，不是判"对话框关掉了" —— 后者是用户点的，
    #   跟任务退没退出毫无关系，第一版那条判据因此**永远绿**（反例法当场漏掉）。
    # [EN] ⚠ Judge **whether the task is still alive**, not "the dialog is closed" -- the latter is the
    # [EN] user's doing and says nothing about the task; the first version was **always green**
    # [EN] (the counterexample caught it).
    _alive_before = bool(getattr(app, '_llm_probe_tick_alive', False))
    page.pop_dialog()
    page.update()
    await asyncio.sleep(1.6)          # 比轮询间隔（0.6s）长，留一次机会让它撞上"已关"
    ok('E1 ★★★ 对话框关掉之后**刷新任务真的退出了**'
       '（`mk_dialog` 的关闭按钮没有回调钩子 ⇒ 靠轮询时发现 `dlg.open` 为假）',
       _alive_before and not bool(getattr(app, '_llm_probe_tick_alive', False)),
       f'关前 alive={_alive_before} · 关后 '
       f'alive={bool(getattr(app, "_llm_probe_tick_alive", False))}')


async def main(page: ft.Page) -> None:
    print('═' * 62)
    print('  点状态条看"这一发 AI 往来"（2026-10-24）')
    print('═' * 62)
    tmp = Path(tempfile.mkdtemp(prefix='nws_llm_probe_'))
    # ★★★ 2026-10-24：**A/B/C 组也必须放进 `try`**。
    #   第一版它们在 try 外面，于是某条变异让 B 组抛 `IndexError` 时，
    #   `main()` 整个抛出去 ⇒ `finally` 里的 `shutdown(page)` **根本没跑** ⇒
    #   Flet 窗口一直开着、判据进程不退 ⇒ 反例法等它 6 分 50 秒（最后被我 kill）。
    #   "判据脚本自己崩了也要能收尾" —— 这条对**每一组**都成立，不是只对真机那几组。
    # [EN] ★★★ 2026-10-24: **A/B/C must also sit inside `try`**. In the first version they were
    # [EN] outside, so when a mutation made group B raise `IndexError`, `main()` propagated, the
    # [EN] `shutdown(page)` in `finally` **never ran**, the Flet window stayed open, the criterion
    # [EN] process never exited, and the counterexample run waited 6m50s (I had to kill it).
    # [EN] "A criterion script must wrap up even when it crashes" applies to **every** group, not just
    # [EN] the real-machine ones.
    try:
        a_clickable()
        b_full_text()
        c_pairing()
        await de_dialog(page)
    except Exception as e:                                       # noqa: BLE001
        import traceback
        traceback.print_exc()
        ok(f'有一组没跑完：{e!r}', False, '')
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        bad = [r for r in _rows if not r['通过']]
        print('\n' + '─' * 62)
        print(f'  AI 往来对话框验证：{len(_rows) - len(bad)}/{len(_rows)}'
              + ('   ← 有失败' if bad else ''))
        for r in bad:
            print(f'    ! {r["判据"]}  [{r["实测"]}]')
        print('─' * 62)
        OUT.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(_rows, ensure_ascii=False, indent=2),
                          encoding='utf-8')
        await shutdown(page, code=0 if not bad else 1)


if __name__ == '__main__':
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
